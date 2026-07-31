import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "..");
const manifestPath = join(repositoryRoot, "manifest.json");
const skillsRoot = join(repositoryRoot, "skills");
const distRoot = join(repositoryRoot, "dist");
const stagingRoot = join(distRoot, "public-skills");
const releaseTag = process.argv[2];
const validateOnly = process.argv.includes("--validate-only");

function fail(message) {
  throw new Error(message);
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function parseSkillFrontmatter(path) {
  const content = readFileSync(path, "utf8");
  const name = content.match(/^name:\s*(.+)$/m)?.[1]?.trim();
  const description = content.match(/^description:\s*(.+)$/m)?.[1]?.trim();
  return { name, description };
}

function validateManifest(manifest) {
  if (manifest.schemaVersion !== 1) fail("manifest.schemaVersion must be 1");
  if (manifest.package !== "lywork-public-skills") fail("Unexpected package name");
  if (!/^\d+\.\d+\.\d+$/.test(manifest.version)) fail("Version must use semantic versioning");
  if (releaseTag && releaseTag !== `v${manifest.version}`) {
    fail(`Release tag ${releaseTag} does not match manifest version v${manifest.version}`);
  }
  if (!Array.isArray(manifest.skills) || manifest.skills.length === 0) {
    fail("manifest.skills must contain at least one Skill");
  }

  const declaredNames = new Set();
  const declaredDirectories = new Set();
  for (const skill of manifest.skills) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skill.name) || skill.name.length > 64) {
      fail(`Invalid Skill name: ${skill.name}`);
    }
    if (declaredNames.has(skill.name)) fail(`Duplicate Skill name: ${skill.name}`);
    if (declaredDirectories.has(skill.directory)) {
      fail(`Duplicate Skill directory: ${skill.directory}`);
    }
    if (skill.directory !== skill.name) {
      fail(`Skill directory must match its name: ${skill.name}`);
    }

    const skillFile = join(skillsRoot, skill.directory, "SKILL.md");
    if (!existsSync(skillFile)) fail(`Missing ${skill.directory}/SKILL.md`);
    const frontmatter = parseSkillFrontmatter(skillFile);
    if (frontmatter.name !== skill.name) {
      fail(`Frontmatter name mismatch in ${skill.directory}/SKILL.md`);
    }
    if (!frontmatter.description || frontmatter.description.length > 1024) {
      fail(`Invalid description in ${skill.directory}/SKILL.md`);
    }

    declaredNames.add(skill.name);
    declaredDirectories.add(skill.directory);
  }

  const actualDirectories = readdirSync(skillsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
  const declared = [...declaredDirectories].sort();
  if (JSON.stringify(actualDirectories) !== JSON.stringify(declared)) {
    fail("Every top-level skills directory must be declared in manifest.json");
  }
}

const manifest = readJson(manifestPath);
validateManifest(manifest);

if (validateOnly) {
  console.log(`Validated ${manifest.skills.length} Skills for v${manifest.version}`);
  process.exit(0);
}

if (!releaseTag) fail("A release tag such as v0.1.0 is required");

rmSync(distRoot, { recursive: true, force: true });
mkdirSync(stagingRoot, { recursive: true });

for (const skill of manifest.skills) {
  cpSync(join(skillsRoot, skill.directory), join(stagingRoot, skill.directory), {
    recursive: true,
  });
}

const runtimeManifest = {
  schemaVersion: manifest.schemaVersion,
  package: manifest.package,
  version: manifest.version,
  skills: manifest.skills,
};
writeFileSync(
  join(stagingRoot, ".lywork-public-skills.json"),
  `${JSON.stringify(runtimeManifest, null, 2)}\n`,
  "utf8",
);

const archivePath = join(distRoot, "lywork-public-skills.zip");
execFileSync("zip", ["-q", "-r", archivePath, "."], {
  cwd: stagingRoot,
  stdio: "inherit",
});

const sha256 = createHash("sha256").update(readFileSync(archivePath)).digest("hex");
writeFileSync(
  `${archivePath}.sha256`,
  `${sha256}  lywork-public-skills.zip\n`,
  "utf8",
);

const releaseManifest = {
  schemaVersion: manifest.schemaVersion,
  package: manifest.package,
  version: manifest.version,
  tag: releaseTag,
  asset: "lywork-public-skills.zip",
  sha256,
  installTarget: manifest.installTarget,
  skills: manifest.skills,
};
writeFileSync(
  join(distRoot, "release-manifest.json"),
  `${JSON.stringify(releaseManifest, null, 2)}\n`,
  "utf8",
);

console.log(`Built ${manifest.skills.length} Skills for ${releaseTag}`);
