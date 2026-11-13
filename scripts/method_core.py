"""Pinned, self-contained Method Core exports with transactional local updates.

No network operations, provider configuration, or target-project state writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

LOCK = 'method-core.lock.json'
REPOSITORY = 'https://github.com/phense/method-core.git'


def safe_name(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('invalid export path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {'', '.', '..', '.git', '.engineering-method'} for part in value.split('/')) or value == LOCK:
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


def check(root):
    root = Path(os.path.abspath(root))
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


def synchronize(source, target, revision=None):
    target = Path(os.path.abspath(target))
    if not target.is_dir(): raise ValueError('target root must exist')
    # Preflight all source and target state before the first mutation.
    proposed,blobs = read_source(source,revision)
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
    saved = {path:(path.read_bytes(),path.stat().st_mode&0o777) if path.exists() else None for path in paths}
    # Track only newly created directories, leaving pre-existing user directories intact.
    directories = set()
    for path in paths:
        parent=path.parent
        while parent != target and not parent.exists():
            directories.add(parent);parent=parent.parent
    touched = []
    try:
        for name in sorted(new_names):
            path=target/name;touched.append(path);_replace(path,blobs[name],modes[name])
        for name in sorted(old_names-new_names):
            path=target/name;touched.append(path);path.unlink()
        touched.append(lp);_replace(lp,(json.dumps(proposed,indent=2,sort_keys=True)+'\n').encode(),0o644)
        check(target)
    except (OSError,ValueError):
        for path in reversed(touched):
            previous=saved[path]
            if previous is None:
                if path.exists(): path.unlink()
            else: _replace(path,*previous)
        for directory in sorted(directories,key=lambda p:len(p.parts),reverse=True):
            if directory.exists() and not any(directory.iterdir()): directory.rmdir()
        raise
    return proposed


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-root',type=Path,default=Path.cwd())
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    try:
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
