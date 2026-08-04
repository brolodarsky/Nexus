const fs = require('fs');
const path = require('path');
const AdmZip = require('adm-zip');

const docxPath = path.resolve(__dirname, '../../Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - William Volodarsky.docx');
const zip = new AdmZip(docxPath);
const documentXml = zip.readAsText('word/document.xml');

// Show the first 3000 chars of the document XML to see what's above and around the H1
console.log(documentXml.substring(0, 3000));
