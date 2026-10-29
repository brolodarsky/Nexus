const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { marked } = require('marked');

// ---------------------------------------------------------------------------
// Directory Paths & Discovery
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
// Page Budget & Geometry Constants
// Standard Letter size at 96 DPI: 8.5" x 11" = 816px x 1056px
// CSS @page margin: 0.3in = ~29px each side
// Usable content height per Letter page: 1056 - (2 * 29) = 998px
// ---------------------------------------------------------------------------
const PAGE_HEIGHT_PX = 998;
const PAGE_MARGIN_PX = 29;

// ---------------------------------------------------------------------------
// Render a single markdown file to PDF and return page geometry metrics
// ---------------------------------------------------------------------------
async function renderToPdf(mdPath, browser) {
    const cssPath = path.resolve(__dirname, 'style.css');
    const markdownContent = fs.readFileSync(mdPath, 'utf-8');

    // Remove YAML frontmatter
    const contentWithoutFrontmatter = markdownContent.replace(/^---[\s\S]*?---\r?\n/, '');

    // Remove Obsidian navigation links ("Back to:" lines with wiki-links)
    const contentClean = contentWithoutFrontmatter.replace(/^Back to:.*\r?\n?/m, '');

    // Derive output filenames from source markdown stem
    const baseName = path.basename(mdPath, '.md');
    const parentDir = path.dirname(mdPath);

    const outputPath = path.join(parentDir, `${baseName}.pdf`);
    const downloadsPath = path.join(process.env.USERPROFILE || '', 'Downloads', `${baseName}.pdf`);

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

    // Set viewport width to usable print area (Letter width minus horizontal margins)
    const usableWidth = 816 - (2 * PAGE_MARGIN_PX);
    await page.setViewportSize({ width: usableWidth, height: 1056 });

    await page.setContent(fullHtml, { waitUntil: 'networkidle' });

    // Measure actual rendered scrollHeight before writing PDF
    const contentHeight = await page.evaluate(() => document.body.scrollHeight);

    await page.pdf({
        path: outputPath,
        format: 'Letter',
        printBackground: true,
    });

    await page.close();

    // Calculate page geometry budget metrics
    const totalPages = Math.ceil(contentHeight / PAGE_HEIGHT_PX);
    const lastPageUsed = contentHeight - ((totalPages - 1) * PAGE_HEIGHT_PX);
    const lastPageFillPct = Math.round((lastPageUsed / PAGE_HEIGHT_PX) * 100);
    const roomRemainingPx = (totalPages * PAGE_HEIGHT_PX) - contentHeight;
    // 1 bullet point ≈ 45px at 0.8rem body text + margins
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

    // Mirror copy to user's Downloads directory
    if (downloadsPath) {
        try {
            fs.copyFileSync(outputPath, downloadsPath);
            console.log(`  PDF: ${outputPath}`);
            console.log(`  Copy: ${downloadsPath}`);
        } catch (copyErr) {
            console.warn(`  Warning: Could not copy to Downloads: ${copyErr.message}`);
            console.log(`  PDF: ${outputPath}`);
        }
    }

    return metrics;
}

// ---------------------------------------------------------------------------
// Headless Compiler CLI Entrypoint
// ---------------------------------------------------------------------------
async function main() {
    // Parse arguments: filter flags and capture target file paths
    const args = process.argv.slice(2);
    const flags = new Set(args.filter(arg => arg.startsWith('--')).map(arg => arg.toLowerCase()));
    const fileArgs = args.filter(arg => !arg.startsWith('--'));

    let selected = [];

    if (flags.has('--all') || (fileArgs.length === 0 && !flags.has('--help'))) {
        // Default to batch compiling all portfolio documents when invoked without args
        selected = findRenderableFiles();
    } else if (fileArgs.length > 0) {
        for (const filePath of fileArgs) {
            const resolved = path.resolve(filePath);
            if (fs.existsSync(resolved)) {
                selected.push(resolved);
            } else {
                console.error(`  Warning: File not found: ${resolved}`);
            }
        }
    }

    if (!selected || selected.length === 0) {
        console.log('No renderable documents found.');
        process.exit(0);
    }

    console.log(`\n  Compiling ${selected.length} document(s) to PDF...\n`);

    const browser = await chromium.launch();
    const allMetrics = [];

    for (const file of selected) {
        const baseName = path.basename(file, '.md');
        console.log(`  --- ${baseName} ---`);
        const metrics = await renderToPdf(file, browser);
        allMetrics.push(metrics);
        console.log('');
    }

    await browser.close();

    // Summary table output
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

        // Machine-readable JSON output for Python service and API consumers
        console.log(`  [METRICS_JSON] ${JSON.stringify(allMetrics)}`);
    }
    console.log('');
    console.log('  Done.');
}

main().catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
