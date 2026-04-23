const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { marked } = require('marked');

async function renderResume() {
    const resumePath = path.resolve(__dirname, '../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - Master.md');
    const cssPath = path.resolve(__dirname, 'style.css');
    const outputPath = path.resolve(__dirname, '../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - William Volodarsky.pdf');
    const downloadsPath = path.join(process.env.USERPROFILE, 'Downloads', 'Resume - William Volodarsky.pdf');

    if (!fs.existsSync(resumePath)) {
        console.error('Master resume not found at:', resumePath);
        process.exit(1);
    }

    const markdownContent = fs.readFileSync(resumePath, 'utf-8');

    // Remove YAML frontmatter
    const contentWithoutFrontmatter = markdownContent.replace(/^---[\s\S]*?---\n/, '');

    const htmlContent = marked.parse(contentWithoutFrontmatter);

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

    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.setContent(fullHtml, { waitUntil: 'networkidle' });

    await page.pdf({
        path: outputPath,
        format: 'Letter',
        printBackground: true,
    });

    await browser.close();

    // Copy to Downloads folder
    try {
        fs.copyFileSync(outputPath, downloadsPath);
        console.log('Resume rendered successfully to:', outputPath);
        console.log('Copy saved to Downloads folder:', downloadsPath);
    } catch (copyErr) {
        console.warn('Warning: Could not copy resume to Downloads folder:', copyErr.message);
        console.log('Resume rendered successfully to:', outputPath);
    }
}

renderResume().catch(err => {
    console.error('Error rendering resume:', err);
    process.exit(1);
});
