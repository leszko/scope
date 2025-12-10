#!/usr/bin/env node
/**
 * Regenerate blockmap and latest.yml after external code signing
 *
 * When code signing happens outside of electron-builder (e.g., Azure Trusted Signing),
 * the binary is modified and the checksums become invalid. This script regenerates them.
 *
 * This reuses electron-builder's blockmap tool and follows the same checksum format.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execSync } = require('child_process');

const DIST_DIR = path.join(__dirname, '..', 'dist');

// Reuse Node's crypto for SHA512 (same as electron-builder uses)
function calculateSha512(filePath) {
  const fileBuffer = fs.readFileSync(filePath);
  const hashSum = crypto.createHash('sha512');
  hashSum.update(fileBuffer);
  return hashSum.digest('base64');
}

function findExeFile() {
  const files = fs.readdirSync(DIST_DIR);
  const exeFile = files.find(f => f.endsWith('.exe') && !f.includes('Uninstall'));
  if (!exeFile) {
    throw new Error('No exe file found in dist directory');
  }
  return path.join(DIST_DIR, exeFile);
}

async function regenerateBlockmap(exeFilePath) {
  console.log(`Regenerating blockmap for: ${exeFilePath}`);

  // Use electron-builder's blockmap tool (same tool it uses internally)
  const blockmapPath = `${exeFilePath}.blockmap`;

  try {
    execSync(`npx blockmap --input "${exeFilePath}" --output "${blockmapPath}"`, {
      stdio: 'inherit',
      cwd: path.join(__dirname, '..')
    });
    console.log(`✓ Blockmap regenerated: ${blockmapPath}`);
  } catch (error) {
    console.error('Failed to regenerate blockmap:', error.message);
    throw error;
  }
}

function regenerateLatestYml(exeFilePath) {
  console.log('Regenerating latest.yml...');

  const packageJson = require('../package.json');
  const version = packageJson.version;
  const exeFileName = path.basename(exeFilePath);

  // Calculate checksums (same method electron-builder uses)
  const exeSha512 = calculateSha512(exeFilePath);
  const exeSize = fs.statSync(exeFilePath).size;

  const blockmapPath = `${exeFilePath}.blockmap`;
  const blockmapSize = fs.statSync(blockmapPath).size;

  // Generate latest.yml in the same format electron-builder produces
  const latestYml = `version: ${version}
files:
  - url: ${exeFileName}
    sha512: ${exeSha512}
    size: ${exeSize}
    blockMapSize: ${blockmapSize}
path: ${exeFileName}
sha512: ${exeSha512}
releaseDate: ${new Date().toISOString()}
`;

  const latestYmlPath = path.join(DIST_DIR, 'latest.yml');
  fs.writeFileSync(latestYmlPath, latestYml, 'utf8');
  console.log(`✓ latest.yml regenerated: ${latestYmlPath}`);
}

async function main() {
  try {
    console.log('=== Regenerating checksums after code signing ===\n');

    const exeFilePath = findExeFile();
    console.log(`Found exe file: ${exeFilePath}\n`);

    await regenerateBlockmap(exeFilePath);
    regenerateLatestYml(exeFilePath);

    console.log('\n✓ All checksums regenerated successfully!');
  } catch (error) {
    console.error('\n✗ Error:', error.message);
    process.exit(1);
  }
}

main();
