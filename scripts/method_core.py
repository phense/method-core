"""Pinned, self-contained Method Core exports with transactional local updates.

No network operations, provider configuration, or target-project state writes.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

LOCK = 'method-core.lock.json'
TRANSACTION = '.method-core-transaction'
REPOSITORY = 'https://github.com/phense/method-core.git'


def safe_name(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('invalid export path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {'', '.', '..', '.git', '.engineering-method'} for part in value.split('/')) or value == LOCK or path.parts[0].startswith('.method-core-'):
        raise ValueError(f'unsafe export path: {value}')
    return value


def contained(root, name):
    safe_name(name)
    result = root / name
    for node in (root, *result.parents, result):
        if node.is_symlink():
            raise ValueError(f'symlinked managed path: {name}')
    if result.exists() and not result.is_file():
        raise ValueError(f'managed path is not a file: {name}')
    return result


def lock_path(root):
    path = root / LOCK
    if any(p.is_symlink() for p in (root, *root.parents, path)) or (path.exists() and not path.is_file()):
        raise ValueError('unsafe core lock path')
    return path


def parse_lock(raw):
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get('schema_version') != 1 or payload.get('repository') != REPOSITORY:
        raise ValueError('invalid core lock identity/schema')
    if not isinstance(payload.get('revision'),str) or not re.fullmatch(r'[0-9a-f]{40}',payload['revision']):
        raise ValueError('invalid core revision')
    files = payload.get('files')
    if not isinstance(files,list) or not files:
        raise ValueError('empty or invalid core inventory')
    seen = set()
    for item in files:
        if not isinstance(item,dict): raise ValueError('invalid core inventory entry')
        name = safe_name(item.get('path'))
        if name in seen: raise ValueError('duplicate core export')
        seen.add(name)
        if item.get('mode') not in ('100644','100755') or not isinstance(item.get('sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):
            raise ValueError(f'invalid core hash/mode: {name}')
    return payload


def check(root, *, allow_transaction=False):
    root = Path(os.path.abspath(root))
    if not allow_transaction and (root / TRANSACTION).exists():
        raise ValueError('pending core transaction; run sync-core --recover first')
    lock = parse_lock(lock_path(root).read_bytes())
    for item in lock['files']:
        path = contained(root,item['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'core drift: {item["path"]}')
        if path.stat().st_mode & 0o777 != int(item['mode'],8) & 0o777:
            raise ValueError(f'core mode drift: {item["path"]}')
    return lock


def git(root, *args):
    result = subprocess.run(['git','-C',str(root),*args],capture_output=True,timeout=30)
    if result.returncode: raise ValueError(f'core Git operation failed: {args[0]}')
    return result.stdout


def read_source(source, revision=None):
    revision = git(source,'rev-parse','--verify',(revision or 'HEAD')+'^{commit}').decode().strip()
    manifest = json.loads(git(source,'show',revision+':method-core.json'))
    if not isinstance(manifest,dict) or manifest.get('schema_version') != 1 or manifest.get('name') != 'method-core':
        raise ValueError('invalid core export manifest')
    names = manifest.get('exports')
    if not isinstance(names,list) or not names: raise ValueError('empty core exports')
    names = [safe_name(n) for n in names]
    if len(names) != len(set(names)): raise ValueError('duplicate core export')
    entries = {}
    for row in git(source,'ls-tree','-rz','--full-tree',revision).split(b'\0'):
        if not row: continue
        meta, raw_name = row.split(b'\t',1)
        mode, kind, oid = meta.decode().split()
        entries[raw_name.decode()] = (mode, kind, oid)
    blobs = {}; records = []
    for name in sorted(names):
        mode,kind,oid = entries.get(name,('','',''))
        if kind != 'blob' or mode not in ('100644','100755'): raise ValueError(f'missing or nonregular core export: {name}')
        blobs[name] = git(source,'cat-file','blob',oid)
        records.append({'path':name,'mode':mode,'sha256':hashlib.sha256(blobs[name]).hexdigest()})
    # Reject dirty current exports even when choosing an older committed revision.
    current = json.loads(git(source,'show','HEAD:method-core.json'))
    checked = sorted(set(names + current.get('exports',[]) + ['method-core.json']))
    if git(source,'status','--porcelain','--untracked-files=all','--',*checked).strip():
        raise ValueError('core exports have uncommitted changes')
    lock = {'schema_version':1,'repository':REPOSITORY,'revision':revision,'version':manifest.get('version'),'files':records}
    parse_lock(json.dumps(lock))
    return lock,blobs


def _replace(path, data, mode):
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.method-core-',dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()


@contextmanager
def _target_guard(target):
    # Keep this file permanently: deleting a lock file creates competing inodes.
    path = target / '.method-core-sync.lock'
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('unsafe core synchronization lock')
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(descriptor).st_size == 0: os.write(descriptor, b'0')
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('core synchronization/recovery is already active') from error
        yield
    finally:
        os.close(descriptor)  # Closing releases either OS lock, also on process death.


def _identity(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def _snapshot(path):
    return (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None


def _transaction_path(target):
    path = target / TRANSACTION
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError('unsafe core transaction directory')
    return path


def _end_transaction(transaction, identity):
    # Retire the complete journal atomically. A crash during garbage collection
    # must not leave an active journal with only some of its backups remaining.
    if _identity(transaction) != identity: raise ValueError('core transaction identity changed')
    retired = Path(tempfile.mkdtemp(prefix='.method-core-retired-', dir=transaction.parent))
    retired.rmdir()
    os.rename(transaction, retired)
    shutil.rmtree(retired)


def _begin_transaction(target, saved):
    # Publish complete backups atomically, before changing any managed file.
    transaction = _transaction_path(target)
    if transaction.exists():
        raise ValueError('another core transaction is pending')
    stage = Path(tempfile.mkdtemp(prefix='.method-core-stage-', dir=target))
    stage.chmod(0o700)
    try:
        entries = []
        for index, (path, previous) in enumerate(saved.items()):
            entry = {'path': path.relative_to(target).as_posix(), 'previous': None}
            if previous is not None:
                data, mode = previous
                with (stage / str(index)).open('wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                entry['previous'] = {'mode': mode, 'sha256': hashlib.sha256(data).hexdigest()}
            entries.append(entry)
        with (stage / 'journal.json').open('w') as stream:
            json.dump({'schema_version': 1, 'pid': os.getpid(), 'files': entries}, stream)
            stream.flush(); os.fsync(stream.fileno())
        os.rename(stage, transaction)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    # A competing updater may have finished between preflight and acquiring the
    # transaction. We have written nothing, so discard our backups, never restore them.
    identity = _identity(transaction)
    if any(_snapshot(path) != previous for path, previous in saved.items()):
        _end_transaction(transaction, identity)
        raise ValueError('core target changed during preflight; retry synchronization')
    return identity


def recover_transaction(target):
    target = Path(os.path.abspath(target))
    lock_path(target)
    with _target_guard(target):
        return _recover_transaction(target)


def _recover_transaction(target, *, owner=False):
    target = Path(os.path.abspath(target))
    transaction = _transaction_path(target)
    if not transaction.exists(): return False
    identity = _identity(transaction)
    journal_path = transaction / 'journal.json'
    if journal_path.is_symlink(): raise ValueError('unsafe core transaction journal')
    journal = json.loads(journal_path.read_bytes())
    if journal.get('schema_version') != 1 or not isinstance(journal.get('pid'), int) or journal['pid'] <= 0:
        raise ValueError('invalid core transaction journal')
    if not owner:
        try: os.kill(journal['pid'], 0)
        except ProcessLookupError: pass
        except PermissionError: raise ValueError('core transaction owner is still active')
        else: raise ValueError('core transaction owner is still active')
    entries = journal.get('files')
    if not isinstance(entries, list) or not entries: raise ValueError('invalid transaction inventory')
    saved = []; seen = set()
    # Validate every backup and destination before attempting recovery.
    for index, entry in enumerate(entries):
        name = entry['path']
        path = lock_path(target) if name == LOCK else contained(target, name)
        if name in seen: raise ValueError('duplicate transaction path')
        seen.add(name)
        previous = entry['previous']
        if previous is not None:
            if not isinstance(previous.get('mode'), int) or not 0 <= previous['mode'] <= 0o777: raise ValueError('invalid backup mode')
            backup = transaction / str(index)
            if backup.is_symlink(): raise ValueError('unsafe transaction backup')
            data = backup.read_bytes()
            if hashlib.sha256(data).hexdigest() != previous.get('sha256'): raise ValueError('damaged transaction backup')
            previous = (data, previous['mode'])
        saved.append((path, previous))
    errors = []
    for path, previous in reversed(saved):
        try:
            if _snapshot(path) == previous: continue
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                _replace(path, *previous)
        except OSError as error:
            # Restore the other paths too, retaining all durable backups for retry.
            errors.append(f'{path.relative_to(target)}: {error}')
    if errors: raise OSError('core recovery incomplete; backups retained: ' + '; '.join(errors))
    _end_transaction(transaction, identity)
    return True


def synchronize(source, target, revision=None):
    target = Path(os.path.abspath(target))
    if not target.is_dir(): raise ValueError('target root must exist')
    lock_path(target)
    proposed, blobs = read_source(source, revision)
    with _target_guard(target):
        return _synchronize(target, proposed, blobs)


def _synchronize(target, proposed, blobs):
    target = Path(os.path.abspath(target))
    if not target.is_dir(): raise ValueError('target root must exist')
    # Recovery is explicit: an interrupted update cannot silently become a new one.
    if _transaction_path(target).exists():
        raise ValueError('pending core transaction; run sync-core --recover first')
    lp = lock_path(target)
    prior = check(target) if lp.exists() else {'files':[]}
    old_names = {entry['path'] for entry in prior['files']}
    new_names = {entry['path'] for entry in proposed['files']}
    modes = {entry['path']:int(entry['mode'],8)&0o777 for entry in proposed['files']}
    for name in sorted(old_names | new_names):
        path = contained(target,name)
        if path.exists() and name not in old_names:
            raise ValueError(f'unowned core destination: {name}')
    paths = [contained(target,name) for name in sorted(old_names | new_names)] + [lp]
    saved = {path:_snapshot(path) for path in paths}
    directories = set()
    for path in paths:
        parent=path.parent
        while parent != target and not parent.exists():
            directories.add(parent);parent=parent.parent
    identity = _begin_transaction(target, saved)
    try:
        for name in sorted(new_names): _replace(target/name,blobs[name],modes[name])
        for name in sorted(old_names-new_names): (target/name).unlink()
        _replace(lp,(json.dumps(proposed,indent=2,sort_keys=True)+'\n').encode(),0o644)
        check(target, allow_transaction=True)
    except BaseException:
        _recover_transaction(target, owner=True)
        for directory in sorted(directories,key=lambda p:len(p.parts),reverse=True):
            if directory.exists() and not any(directory.iterdir()): directory.rmdir()
        raise
    _end_transaction(_transaction_path(target), identity)
    return proposed


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-root',type=Path,default=Path.cwd())
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--revision')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--recover',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.recover:
            if args.source_root or args.revision: raise ValueError('--recover is offline; omit source/revision')
            recovered = recover_transaction(args.target_root)
            print(json.dumps({'status':'passed','recovered':recovered}))
            return 0
        if args.check:
            if args.source_root or args.revision: raise ValueError('--check is offline; omit source/revision')
            result=check(args.target_root)
        else:
            if not args.source_root: raise ValueError('--source-root is required for synchronization')
            result=synchronize(args.source_root,args.target_root,args.revision)
        print(json.dumps({'status':'passed','revision':result['revision'],'files':len(result['files'])}))
        return 0
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired) as error:
        print(json.dumps({'status':'failed','error':str(error)}));return 1

if __name__=='__main__': raise SystemExit(main())
