import sys
import os
import xml.etree.ElementTree as ET
from datetime import datetime

def parse_element(el, md_lines):
    tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
    
    if tag == 'paragraph':
        text = "".join(el.itertext()).strip()
        if text:
            md_lines.append(f"\n**{text}**\n")
    elif tag == 'title':
        text = "".join(el.itertext()).strip()
        if text:
            md_lines.append(f"\n## {text}\n")
    elif tag == 'table':
        parse_table(el, md_lines)
    elif tag == 'pre':
        text = "".join(el.itertext())
        # Clean up multi-lines for pre tags specifically to avoid breaking tables if inside one
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            md_lines.append(f"```\n" + "\n".join(lines) + "\n```\n")
    elif tag == 'item':
        text = " ".join("".join(el.itertext()).split())
        if text:
             md_lines.append(f"- {text}")
    else:
        for child in el:
            parse_element(child, md_lines)

def parse_table(table_el, md_lines):
    thead = None
    tbody = None
    for child in table_el:
        c_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if c_tag == 'thead':
            thead = child
        elif c_tag == 'tbody':
            tbody = child

    if thead is not None:
        tr = None
        for child in thead.iter():
            if child.tag.endswith('tr'):
                tr = child
                break

        headers = []
        if tr is not None:
            for th in tr:
                if th.tag.endswith('th') or th.tag.endswith('td'):
                    text = "".join(th.itertext()).strip()
                    headers.append(text if text else "-")
            
            if headers:
                md_lines.append("\n| " + " | ".join(headers) + " |")
                md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")

    if tbody is not None:
        for child in tbody:
            c_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if c_tag == 'tr':
                cells = []
                for td in child:
                    if td.tag.endswith('td') or td.tag.endswith('th'):
                        # Process contents of td
                        text_chunks = []
                        for desc in td.iter():
                            if desc.tag.endswith('pre'):
                                lines = [l.strip() for l in "".join(desc.itertext()).split('\n') if l.strip()]
                                text_chunks.append(" <br> ".join(lines))
                            elif desc.text and desc.text.strip():
                                # Only add if not captured by pre
                                if not any(desc in p.iter() for p in td.iter() if p.tag.endswith('pre')):
                                    text_chunks.append(desc.text.strip())
                        
                        text = " ".join(text_chunks) if text_chunks else " ".join("".join(td.itertext()).split())
                        cells.append(text if text else " ")
                
                if cells:
                    # Fix: Make sure cells line up with headers if headers exist, or just dump them
                    md_lines.append("| " + " | ".join(cells) + " |")
        md_lines.append("\n")

def main():
    if len(sys.argv) < 3:
        print("Usage: python medical_xml_parser.py <input_xml> <output_dir>")
        sys.exit(1)
        
    input_xml = sys.argv[1]
    output_dir = sys.argv[2]
    
    if not os.path.exists(input_xml):
        print(f"File {input_xml} not found!")
        sys.exit(1)
        
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        tree = ET.parse(input_xml)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)
        
    md_lines = []
    
    title = ""
    for el in root.iter():
        tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        if tag == 'title' and not title:
            title = el.text.strip() if el.text else "Medical_Record"
            break
            
    md_lines.append(f"---")
    md_lines.append(f"tags: [health, lab_work]")
    md_lines.append(f"type: log")
    date_str = datetime.now().strftime("%Y-%m-%d")
    md_lines.append(f"date: {date_str}")
    md_lines.append(f"---\n")
    
    md_lines.append(f"# {title}\n")
    
    body_found = False
    for el in root.iter():
        tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        if tag == 'structuredBody':
            body_found = True
            parse_element(el, md_lines)
            break
            
    if not body_found:
        text = "".join(root.itertext())
        md_lines.append(text)
        
    base_name = os.path.basename(input_xml).replace('.xml', '')
    out_file = os.path.join(output_dir, f"{date_str} - {base_name}.md")
    
    # Filter empty lines for neatness
    final_output = []
    for line in md_lines:
        if final_output and final_output[-1].strip() == "" and line.strip() == "":
            continue
        final_output.append(line)
        
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(final_output))
        
    print(f"Successfully wrote markdown to {out_file}")

if __name__ == '__main__':
    main()
