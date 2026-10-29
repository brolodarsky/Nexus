const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { execSync } = require('child_process');
const { chromium } = require('playwright');
const { marked } = require('marked');

// ---------------------------------------------------------------------------
// Scan directories for renderable documents
// ---------------------------------------------------------------------------
const PORTFOLIO_DIR = path.resolve(__dirname, '../../../../Vault/3. Operations/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence');
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
// Page measurement constants
// Letter size at 96 DPI: 8.5" x 11" = 816px x 1056px
// CSS @page margin: 0.3in on all sides = 28.8px each
// Usable content height per page: 1056 - (2 * 28.8) = 998.4px
// ---------------------------------------------------------------------------
const PAGE_HEIGHT_PX = 998;
const PAGE_MARGIN_PX = 29; // 0.3in at 96 DPI

// ---------------------------------------------------------------------------
// Render a single markdown file to PDF and return page metrics
// ---------------------------------------------------------------------------
async function renderToPdf(mdPath, browser) {
    const cssPath = path.resolve(__dirname, 'style.css');
    const markdownContent = fs.readFileSync(mdPath, 'utf-8');

    // Remove YAML frontmatter
    const contentWithoutFrontmatter = markdownContent.replace(/^---[\s\S]*?---\r?\n/, '');

    // Remove Obsidian navigation links (the "Back to:" line with wiki-links)
    const contentClean = contentWithoutFrontmatter.replace(/^Back to:.*\r?\n?/m, '');

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

    // Set viewport to match Letter width minus horizontal margins for accurate measurement
    const usableWidth = 816 - (2 * PAGE_MARGIN_PX); // Letter width at 96 DPI minus margins
    await page.setViewportSize({ width: usableWidth, height: 1056 });

    await page.setContent(fullHtml, { waitUntil: 'networkidle' });

    // Measure content height before generating PDF
    const contentHeight = await page.evaluate(() => document.body.scrollHeight);

    await page.pdf({
        path: outputPath,
        format: 'Letter',
        printBackground: true,
    });

    await page.close();

    // Calculate page metrics
    const totalPages = Math.ceil(contentHeight / PAGE_HEIGHT_PX);
    const lastPageUsed = contentHeight - ((totalPages - 1) * PAGE_HEIGHT_PX);
    const lastPageFillPct = Math.round((lastPageUsed / PAGE_HEIGHT_PX) * 100);
    const roomRemainingPx = (totalPages * PAGE_HEIGHT_PX) - contentHeight;
    // Approximate: 1 bullet point ≈ 45px at 0.8rem body + 1.0 line-height + margins
    const approxBulletsRemaining = Math.floor(roomRemainingPx / 45);

    let verdict;
    if (lastPageFillPct < 60) verdict = 'UNDERFILL';
    else if (lastPageFillPct <= 80) verdict = 'ROOM';
    else if (lastPageFillPct <= 95) verdict = 'GOOD FIT';
    else if (lastPageFillPct <= 100) verdict = 'TIGHT FIT';
    else verdict = 'OVERFLOW';

    const metrics = {
        file: baseName,
        pages: totalPages,
        contentHeightPx: contentHeight,
        pageHeightPx: PAGE_HEIGHT_PX,
        lastPageFillPct,
        roomRemainingPx,
        approxBulletsRemaining,
        verdict,
    };

    // Copy to Downloads folder
    try {
        fs.copyFileSync(outputPath, downloadsPath);
        console.log(`  PDF: ${outputPath}`);
        console.log(`  Copy: ${downloadsPath}`);
    } catch (copyErr) {
        console.warn(`  Warning: Could not copy to Downloads: ${copyErr.message}`);
        console.log(`  PDF: ${outputPath}`);
    }

    return metrics;
}

// ---------------------------------------------------------------------------
// Render a single markdown file to DOCX via the Python renderer
// ---------------------------------------------------------------------------
function renderToDocx(mdPath) {
    const pythonPath = path.resolve(__dirname, '../../../../.venv/Scripts/python.exe');
    const scriptPath = path.resolve(__dirname, 'render_docx.py');

    try {
        execSync(`"${pythonPath}" "${scriptPath}" "${mdPath}"`, { stdio: 'inherit' });
    } catch (docxErr) {
        console.error(`  DOCX error: ${docxErr.message}`);
    }
}

// ---------------------------------------------------------------------------
// Main Entrypoint — Supports interactive CLI, programmatic CLI args, and flags
// ---------------------------------------------------------------------------
async function main() {
    // Parse arguments: filter out execution flags (prefixed with --) and extract file path arguments
    // process.argv.slice(2): Strips node runtime path and script file path
    const args = process.argv.slice(2);
    const flags = new Set(args.filter(arg => arg.startsWith('--')).map(arg => arg.toLowerCase()));
    const fileArgs = args.filter(arg => !arg.startsWith('--'));

    const isPdfOnly = flags.has('--pdf-only');
    const isDocxOnly = flags.has('--docx-only');
    const isAll = flags.has('--all');

    let selected = [];

    if (isAll) {
        // --all flag: batch-render all discovered resumes and cover letters across the portfolio
        selected = findRenderableFiles();
    } else if (fileArgs.length > 0) {
        // Positional file paths: resolve each target and verify physical disk presence
        for (const filePath of fileArgs) {
            const resolved = path.resolve(filePath);
            if (fs.existsSync(resolved)) {
                selected.push(resolved);
            } else {
                console.error(`  Warning: File not found: ${resolved}`);
            }
        }
    } else {
        // Interactive terminal picker when invoked with no command line arguments
        const files = findRenderableFiles();

        if (files.length === 0) {
            console.log('No renderable documents found.');
            process.exit(0);
        }

        selected = await promptFileSelection(files);
    }

    if (!selected || selected.length === 0) {
        process.exit(0);
    }

    console.log(`\n  Rendering ${selected.length} document(s)...\n`);

    // Headless Chromium browser instance only required if PDF rendering or metric measurement is needed
    const needsBrowser = !isDocxOnly;
    const browser = needsBrowser ? await chromium.launch() : null;
    const allMetrics = [];

    for (const file of selected) {
        const baseName = path.basename(file, '.md');
        console.log(`  --- ${baseName} ---`);

        // 1. PDF Compilation & Geometry Budget Measurement
        if (browser && !isDocxOnly) {
            const metrics = await renderToPdf(file, browser);
            allMetrics.push(metrics);
        }

        // 2. Word DOCX Compilation
        if (!isPdfOnly) {
            renderToDocx(file);
        }
        console.log('');
    }

    if (browser) {
        await browser.close();
    }

    // Print human-readable page metrics summary table
    if (allMetrics.length > 0) {
        console.log('  ' + '═'.repeat(60));
        console.log('  📐 PAGE METRICS');
        console.log('  ' + '═'.repeat(60));
        for (const m of allMetrics) {
            const icon = m.verdict === 'GOOD FIT' ? '✅' :
                         m.verdict === 'TIGHT FIT' ? '🎯' :
                         m.verdict === 'ROOM' ? '📝' :
                         m.verdict === 'UNDERFILL' ? '⚠️' : '🔴';
            console.log(`  ${icon} ${m.file}`);
            console.log(`     Pages: ${m.pages} | Last page fill: ${m.lastPageFillPct}% | Verdict: ${m.verdict}`);
            if (m.approxBulletsRemaining > 0) {
                console.log(`     Room: ~${m.approxBulletsRemaining} bullet points remaining (~${m.roomRemainingPx}px)`);
            } else if (m.lastPageFillPct > 100) {
                console.log(`     Over by ~${Math.abs(m.roomRemainingPx)}px — trim ~${Math.ceil(Math.abs(m.roomRemainingPx) / 45)} bullet points`);
            }
        }
        console.log('  ' + '─'.repeat(60));

        // Output machine-readable JSON for agent consumption and backend API parsing
        console.log(`  [METRICS_JSON] ${JSON.stringify(allMetrics)}`);
    }
    console.log('');
    console.log('  Done.');
}

main().catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
