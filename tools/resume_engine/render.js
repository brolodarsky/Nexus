const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { execSync } = require('child_process');
const { chromium } = require('playwright');
const { marked } = require('marked');

// ---------------------------------------------------------------------------
// Scan directories for renderable documents
// ---------------------------------------------------------------------------
const PORTFOLIO_DIR = path.resolve(__dirname, '../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence');
const RESUMES_DIR = path.join(PORTFOLIO_DIR, 'Resumes');
const COVER_LETTERS_DIR = path.join(PORTFOLIO_DIR, 'Cover Letters');

function scanDir(dir) {
    const files = [];
    if (!fs.existsSync(dir)) return files;
    for (const entry of fs.readdirSync(dir)) {
        if (entry.endsWith('.md')) {
            files.push(path.join(dir, entry));
        }
    }
    return files;
}

function findRenderableFiles() {
    return [
        ...scanDir(RESUMES_DIR),
        ...scanDir(COVER_LETTERS_DIR),
    ].sort();
}

// ---------------------------------------------------------------------------
// Interactive file picker
// ---------------------------------------------------------------------------
function createInterface() {
    return readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });
}

async function promptFileSelection(files) {
    const rl = createInterface();

    console.log('\n  Resume Engine - Document Renderer');
    console.log('  ---------------------------------\n');
    console.log('  Found renderable documents:\n');

    files.forEach((f, i) => {
        const rel = path.relative(PORTFOLIO_DIR, f);
        console.log(`    [${i + 1}] ${rel}`);
    });

    console.log(`\n    [a] Render all`);
    console.log(`    [q] Quit\n`);

    return new Promise((resolve) => {
        rl.question('  Select document(s) (comma-separated numbers, "a" for all): ', (answer) => {
            rl.close();
            const input = answer.trim().toLowerCase();

            if (input === 'q') {
                resolve([]);
                return;
            }

            if (input === 'a') {
                resolve(files);
                return;
            }

            const indices = input.split(',').map(s => parseInt(s.trim(), 10) - 1);
            const selected = indices
                .filter(i => i >= 0 && i < files.length)
                .map(i => files[i]);

            if (selected.length === 0) {
                console.log('  No valid selection. Exiting.');
            }

            resolve(selected);
        });
    });
}

// ---------------------------------------------------------------------------
// Render a single markdown file to PDF
// ---------------------------------------------------------------------------
async function renderToPdf(mdPath, browser) {
    const cssPath = path.resolve(__dirname, 'style.css');
    const markdownContent = fs.readFileSync(mdPath, 'utf-8');

    // Remove YAML frontmatter
    const contentWithoutFrontmatter = markdownContent.replace(/^---[\s\S]*?---\n/, '');

    // Remove Obsidian navigation links (the "Back to:" line with wiki-links)
    const contentClean = contentWithoutFrontmatter.replace(/^Back to:.*\n?/m, '');

    // Derive output filename from the source filename
    const baseName = path.basename(mdPath, '.md');
    const parentDir = path.dirname(mdPath);

    const outputPath = path.join(parentDir, `${baseName}.pdf`);
    const downloadsPath = path.join(process.env.USERPROFILE, 'Downloads', `${baseName}.pdf`);

    const htmlContent = marked.parse(contentClean);

    const fullHtml = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            ${fs.readFileSync(cssPath, 'utf-8')}
        </style>
    </head>
    <body>
        <div class="container">
            ${htmlContent}
        </div>
    </body>
    </html>
    `;

    const page = await browser.newPage();
    await page.setContent(fullHtml, { waitUntil: 'networkidle' });

    await page.pdf({
        path: outputPath,
        format: 'Letter',
        printBackground: true,
    });

    await page.close();

    // Copy to Downloads folder
    try {
        fs.copyFileSync(outputPath, downloadsPath);
        console.log(`  PDF: ${outputPath}`);
        console.log(`  Copy: ${downloadsPath}`);
    } catch (copyErr) {
        console.warn(`  Warning: Could not copy to Downloads: ${copyErr.message}`);
        console.log(`  PDF: ${outputPath}`);
    }

    return outputPath;
}

// ---------------------------------------------------------------------------
// Render a single markdown file to DOCX via the Python renderer
// ---------------------------------------------------------------------------
function renderToDocx(mdPath) {
    const pythonPath = path.resolve(__dirname, '../../.venv/Scripts/python.exe');
    const scriptPath = path.resolve(__dirname, 'render_docx.py');

    try {
        execSync(`"${pythonPath}" "${scriptPath}" "${mdPath}"`, { stdio: 'inherit' });
    } catch (docxErr) {
        console.error(`  DOCX error: ${docxErr.message}`);
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
    const files = findRenderableFiles();

    if (files.length === 0) {
        console.log('No renderable documents found.');
        process.exit(0);
    }

    // Support passing a path directly as a CLI argument (for workflow/script use)
    let selected;
    if (process.argv[2]) {
        const target = path.resolve(process.argv[2]);
        if (fs.existsSync(target)) {
            selected = [target];
        } else {
            console.error(`File not found: ${target}`);
            process.exit(1);
        }
    } else {
        selected = await promptFileSelection(files);
    }

    if (selected.length === 0) {
        process.exit(0);
    }

    console.log(`\n  Rendering ${selected.length} document(s)...\n`);

    const browser = await chromium.launch();

    for (const file of selected) {
        const baseName = path.basename(file, '.md');
        console.log(`  --- ${baseName} ---`);

        await renderToPdf(file, browser);
        renderToDocx(file);
        console.log('');
    }

    await browser.close();
    console.log('  Done.');
}

main().catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
