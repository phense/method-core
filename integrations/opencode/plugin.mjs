import { realpathSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Follow a linked loader back to the retained package, preserving SKILL.md links.
const root = resolve(dirname(realpathSync(fileURLToPath(import.meta.url))), "../..");

export default async function engineeringMethod() {
  return {
    async config(config) {
      config.skills ??= {};
      config.skills.paths ??= [];
      const skills = resolve(root, "skills");
      if (!config.skills.paths.includes(skills)) config.skills.paths.push(skills);

      config.instructions ??= [];
      const adapter = resolve(root, "shared/platform/opencode.md");
      if (!config.instructions.includes(adapter)) config.instructions.push(adapter);
    },
  };
}
