"""Legacy translator untuk object diagram.

Implementasi xtUML yang lebih lengkap ada di paket `xtuml_compiler`.
File ini dipertahankan hanya untuk kompatibilitas dengan pemanggil lama.
"""

import re
import json
import xml.etree.ElementTree as ET

def parse_json(text):
    """Memproses format JSON"""
    data = json.loads(text)
    objects = data.get("objects", [])
    links = data.get("links", [])
    return objects, links

def parse_plantuml(text):
    """Memproses format teks PlantUML"""
    objects, links = [], []
    
    # Match object { attr = val }
    object_pattern = r'object\s+(\w+)\s*\{([^}]+)\}'
    matches = re.findall(object_pattern, text)

    for obj_name, attr_block in matches:
        attributes = {}
        for line in attr_block.strip().split('\n'):
            line = line.strip()
            if '=' in line:
                key, val = line.split('=', 1)
                key, val = key.strip(), val.strip().strip('"\'')
                
                # Konversi tipe data otomatis
                if val.isdigit():
                    val = int(val)
                elif val.lower() in ['true', 'false']:
                    val = val.lower() == 'true'
                
                attributes[key] = val

        objects.append({
            "name": obj_name,
            "className": obj_name.capitalize(),
            "attributes": attributes
        })

    # Match obj1 -- obj2 : relation
    link_pattern = r'(\w+)\s*--\s*(\w+)\s*:\s*(\w+)'
    link_matches = re.findall(link_pattern, text)

    for src, target, rel_name in link_matches:
        links.append({"from": src, "to": target, "relation": rel_name})

    return objects, links


def parse_xml(xml_text):
    """Memproses format file XML UML"""
    objects, links = [], []
    id_map = {}

    root = ET.fromstring(xml_text)

    for obj in root.findall('.//object'):
        obj_id = obj.attrib.get('id', '')
        obj_name = obj.attrib.get('name', 'obj')
        obj_class = obj.attrib.get('class', 'Object')
        
        if obj_id:
            id_map[obj_id] = obj_name

        attributes = {}
        for attr in obj.findall('attribute'):
            attr_name = attr.attrib.get('name')
            attr_val = attr.text if attr.text is not None else ""
            
            if attr_val.isdigit():
                attr_val = int(attr_val)
            elif attr_val.lower() in ['true', 'false']:
                attr_val = attr_val.lower() == 'true'

            attributes[attr_name] = attr_val

        objects.append({
            "name": obj_name,
            "className": obj_class,
            "attributes": attributes
        })

    for link in root.findall('.//link'):
        src_id = link.attrib.get('source')
        target_id = link.attrib.get('target')
        relation = link.attrib.get('relation', 'link')

        src_name = id_map.get(src_id, src_id)
        target_name = id_map.get(target_id, target_id)

        links.append({"from": src_name, "to": target_name, "relation": relation})

    return objects, links


def compile_uml_to_js(input_text):
    """Fungsi Utama Compiler (Auto-Detect Format)"""
    clean_input = input_text.strip()
    if not clean_input:
        return False, "Input masih kosong! Masukkan kode UML terlebih dahulu."

    try:
        # Deteksi otomatis format input
        if clean_input.startswith("{"):
            objects, links = parse_json(clean_input)
            source_type = "JSON"
        elif clean_input.startswith("<?xml") or clean_input.startswith("<"):
            objects, links = parse_xml(clean_input)
            source_type = "XML"
        else:
            objects, links = parse_plantuml(clean_input)
            source_type = "PlantUML"

        if not objects:
            return False, f"Tidak ada objek UML yang terdeteksi dari input format {source_type}!"

        # Generasi Kode JavaScript Output
        js_code = f"// ====================================\n"
        js_code += f"// Generated JavaScript from {source_type}\n"
        js_code += f"// ====================================\n\n"

        for obj in objects:
            js_code += f"// Instance: {obj['name']}\n"
            js_code += f"const {obj['name']} = {{\n"
            js_code += f'  _class: "{obj.get("className", "Object")}",\n'
            for k, v in obj.get("attributes", {}).items():
                if isinstance(v, str):
                    val_str = f'"{v}"'
                elif isinstance(v, bool):
                    val_str = "true" if v else "false"
                else:
                    val_str = str(v)
                js_code += f"  {k}: {val_str},\n"
            js_code += "};\n\n"

        if links:
            js_code += "// Relationships\n"
            for link in links:
                js_code += f"{link['from']}.{link['relation']} = {link['to']};\n"

        return True, js_code

    except json.JSONDecodeError as e:
        return False, f"Error Format JSON Tidak Valid: {str(e)}"
    except ET.ParseError as e:
        return False, f"Error Format XML Tidak Valid: {str(e)}"
    except Exception as e:
        return False, f"Error Compiling UML: {str(e)}"