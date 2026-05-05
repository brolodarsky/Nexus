const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { marked } = require('marked');
const HTMLtoDOCX = require('html-to-docx');

async function renderResume() {
    const resumePath = path.resolve(__dirname, '../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - Master.md');
    const cssPath = path.resolve(__dirname, 'style.css');

    if (!fs.existsSync(resumePath)) {
        console.error('Master resume not found at:', resumePath);
        process.exit(1);
    }

    const markdownContent = fs.readFileSync(resumePath, 'utf-8');

    // Remove YAML frontmatter
    const contentWithoutFrontmatter = markdownContent.replace(/^---[\s\S]*?---\n/, '');

    // Extract title from first H1
    const titleMatch = contentWithoutFrontmatter.match(/^#\s+(.+)$/m);
    const resumeTitle = titleMatch ? titleMatch[1].trim() : 'Master';
    const sanitizedTitle = resumeTitle.replace(/[\\/:*?"<>|]/g, '');

    const outputPath = path.resolve(__dirname, `../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - ${sanitizedTitle}.pdf`);
    const downloadsPath = path.join(process.env.USERPROFILE, 'Downloads', `Resume - ${sanitizedTitle}.pdf`);

    const docxOutputPath = path.resolve(__dirname, `../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - ${sanitizedTitle}.docx`);
    const docxDownloadsPath = path.join(process.env.USERPROFILE, 'Downloads', `Resume - ${sanitizedTitle}.docx`);

    let htmlContent = marked.parse(contentWithoutFrontmatter);
    // html-to-docx relies on inline styles to override Word's default huge spacing for headings
    htmlContent = htmlContent.replace(/<h1(.*?)>/g, '<h1$1 style="margin-top: 0; padding-top: 0;">');

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

    // Generate and save DOCX
    try {
        const docxBuffer = await HTMLtoDOCX(fullHtml, null, {
            table: { row: { cantSplit: true } },
            footer: true,
            pageNumber: true,
            margins: {
                top: 720,
                right: 720,
                bottom: 720,
                left: 720,
                header: 720,
                footer: 720,
                gutter: 0
            }
        });
        fs.writeFileSync(docxOutputPath, docxBuffer);
        
        try {
            fs.copyFileSync(docxOutputPath, docxDownloadsPath);
            console.log('DOCX resume rendered successfully to:', docxOutputPath);
            console.log('DOCX copy saved to Downloads folder:', docxDownloadsPath);
        } catch (copyErr) {
            console.warn('Warning: Could not copy DOCX resume to Downloads folder:', copyErr.message);
            console.log('DOCX resume rendered successfully to:', docxOutputPath);
        }
    } catch (docxErr) {
        console.error('Error generating DOCX resume:', docxErr);
    }

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
