import sys
import json
import os
import glob
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright
import requests
from typing import List

def ejecutar_render(slides, ratio):
    # Dimensiones base estandarizadas en redes sociales
    dims = {
        '1:1': {'width': 1080, 'height': 1080}, 
        '4:5': {'width': 1080, 'height': 1350},
        '16:9': {'width': 1920, 'height': 1080},
        '9:16': {'width': 1080, 'height': 1920}
    }
    selected_dim = dims.get(ratio, dims['4:5'])
    generated_files = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport=selected_dim,
            device_scale_factor=2
        )
        page = context.new_page()
        
        for i, html_content in enumerate(slides):
            page.set_content(html_content)
            page.wait_for_load_state('networkidle')
            page.evaluate("document.body.style.margin = '0'; document.body.style.padding = '0';")
            
            output_path = f"/home/node/.n8n-files/slide_{i+1}.png"
            page.screenshot(path=output_path, full_page=False)
            generated_files.append(output_path)
            
        browser.close()
    return generated_files

def extract_json_payload(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.split('\n')[1:-1])
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError('No se encontró un objeto JSON válido en la respuesta del modelo.')
    raw_json = text[start:end + 1]
    
    # Habilitamos strict=False para tolerar saltos de línea crudos en los strings
    return json.loads(raw_json, strict=False)


def generar_diseno_local(platform, theme, aspect_ratio, slides_count, chat_id):
    api_url = os.environ.get(
        "LMSTUDIO_API_URL",
        "[http://host.docker.internal:1234/v1/chat/completions](http://host.docker.internal:1234/v1/chat/completions)"
    )
    model = os.environ.get("LMSTUDIO_MODEL", "qwen/qwen3.5-9b")

    # 1. Cargar imágenes de templates/estilos visuales para referencia de estilo
    templates_dir = "/home/node/.n8n-files/templates"
    template_files = glob.glob(os.path.join(templates_dir, "*"))
    template_images = []
    for path in template_files[:4]:
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            try:
                mime_type = "image/png" if ext == ".png" else "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp"
                with open(path, "rb") as f:
                    data = f.read()
                b64_encoded = base64.b64encode(data).decode("utf-8")
                template_images.append({
                    "name": os.path.basename(path),
                    "url": f"data:{mime_type};base64,{b64_encoded}",
                })
            except Exception as e:
                print(f"Error cargando template {path}: {e}")

    # 2. Cargar imágenes enviadas por el usuario para este chat_id
    user_inputs_dir = "/home/node/.n8n-files/user_inputs"
    user_files = glob.glob(os.path.join(user_inputs_dir, f"input_image_{chat_id}_*"))
    user_images = []
    for path in user_files[:4]:
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            try:
                mime_type = "image/png" if ext == ".png" else "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp"
                with open(path, "rb") as f:
                    data = f.read()
                b64_encoded = base64.b64encode(data).decode("utf-8")
                user_images.append({
                    "name": os.path.basename(path),
                    "url": f"data:{mime_type};base64,{b64_encoded}",
                })
            except Exception as e:
                print(f"Error cargando imagen de usuario {path}: {e}")

    # 3. Cargar el Logo SVG dinámico de CyberMinds
    logo_dir = "./data/n8n_shared_data/logo"
    logo_svg_content = ""
    if os.path.exists(logo_dir):
        svg_files = glob.glob(os.path.join(logo_dir, "*.svg"))
        if svg_files:
            try:
                with open(svg_files[0], "r", encoding="utf-8") as f:
                    logo_svg_content = f.read()
            except Exception as e:
                print(f"Error cargando el logo SVG desde {svg_files[0]}: {e}")

    prompt_text = f"""
    Eres un Director de Arte de vanguardia y Diseñador de Contenido Senior para marcas de Ciberseguridad de alto impacto (Estilo HorseCiab / CyberMinds).
    Tu objetivo es romper el aspecto genérico de "diseño de IA" y generar piezas con fuerza editorial, tipografía masiva y contrastes agresivos.

    DATOS DEL POST:
    - Plataforma destino: {platform}
    - Tema central / Contexto: {theme}
    - Relación de Aspecto: {aspect_ratio}
    - Cantidad de Slides Planificados: {slides_count}

    REGLAS ESTRICTAS DE DISEÑO VISUAL (Para evitar desbordes y fuentes pequeñas):
    1. Tipografía Monumental e Impactante:
       - Los títulos principales deben ser gigantescos (`font-size: 4.5rem` a `6rem` o `10vw`), en negrita tipográfica absoluta (p. ej., 'Syne' o 'Orbitron' con `font-weight: 900`).
       - Los textos secundarios deben ser limpios, contrastantes ('Inter' o 'Space Grotesk') and con un tamaño sumamente legible (mínimo `1.5rem` o `24px`).
    2. Composición Editorial y Control de Bordes (Anti-Overflow):
       - Cada slide debe usar un contenedor maestro con: `box-sizing: border-box; padding: 80px 60px; display: flex; flex-direction: column; justify-content: space-between; height: 100vh; width: 100vw; overflow: hidden;`.
       - Queda estrictamente PROHIBIDO que los textos o recuadros toquen o se salgan de los bordes físicos del lienzo.
       - No uses cajas flotantes pequeñas con brillos de neón saturados en el medio del lienzo.
    3. Fondos Inmersivos de Ciberseguridad:
       - No uses fondos negros planos con círculos difuminados de colores aleatorios. Usa texturas de código atenuado, patrones de rejillas tecnológicas (grids), abstracciones de circuitos o imágenes de fondo oscurecidas con un gradiente negro encima.
    """

    if template_images:
        prompt_text += f"\n    A. IMÁGENES DE REFERENCIA DE DISEÑO (TEMPLATES): {len(template_images)} archivo(s).\n"
        prompt_text += "    Estas imágenes están adjuntas para guiar el estilo visual del diseño.\n"
        for item in template_images:
            prompt_text += f"       - {item['name']}\n"

    if user_images:
        prompt_text += "\n    B. IMÁGENES DEL USUARIO PARA INCLUIR EN EL DISEÑO:\n"
        prompt_text += "    Estas imágenes están adjuntas y deben influir en la composición final.\n"
        for item in user_images:
            prompt_text += f"       - {item['name']}\n"
    else:
        prompt_text += "\n    Nota: El usuario no ha subido imágenes específicas en esta ejecución. Genera el diseño usando maquetación e iconografía puramente vectorial.\n"

    if logo_svg_content:
        prompt_text += "\n    C. INCLUSIÓN OBLIGATORIA DEL LOGO (CYBERMINDS):\n"
        prompt_text += "    Inserta este SVG directamente en cada slide y ajusta el color para asegurar contraste.\n"
        prompt_text += f"    SVG:\n{logo_svg_content}\n"

    prompt_text += "\n    Debes responder únicamente con un documento JSON válido que contenga las claves 'copy' y 'slides'.\n"
    prompt_text += "    La clave 'slides' debe ser una lista de HTML5 completos, cada uno independiente y apto para renderizar con Playwright.\n"

    system_instruction = (
        f"Eres un asistente de diseño que genera contenido HTML y texto para posts de redes sociales. "
        f"Devuelve exclusivamente un JSON válido con los campos 'copy' y 'slides'. "
        f"No agregues explicaciones adicionales."
    )

    content_parts = [{"type": "text", "text": prompt_text}]
    for item in template_images + user_images:
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": item["url"],
                "detail": "high",
            },
        })

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": content_parts},
        ],
        "temperature": 0.4,
        "max_tokens": 8192,
    }

    response = requests.post(api_url, json=payload, timeout=600)
    response.raise_for_status()
    response_data = response.json()

    if "choices" not in response_data or not response_data["choices"]:
        raise ValueError("Respuesta inválida de LM Studio: no se devolvieron choices.")

    choice = response_data["choices"][0]
    content = ""
    if isinstance(choice, dict):
        message = choice.get("message", {})
        content = message.get("content") or message.get("text", "")
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            content = "".join(text_parts)
        elif not isinstance(content, str):
            content = json.dumps(content)

    if not content:
        raise ValueError("LM Studio no devolvió contenido de texto.")

    result = extract_json_payload(content)
    
    # Sanitización / Normalización del campo copy
    copy_data = result.get("copy", "")
    if isinstance(copy_data, dict):
        parts = []
        if "headline" in copy_data: parts.append(f"*{copy_data['headline']}*")
        if "subhead" in copy_data: parts.append(copy_data["subhead"])
        if "cta" in copy_data: parts.append(f"🚀 {copy_data['cta']}")
        copy_data = "\n\n".join(parts)
    elif not isinstance(copy_data, str):
        copy_data = str(copy_data)

    return copy_data, result.get("slides", []), user_files

class RenderHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
        
        if "theme" in post_data:
            try:
                platform = post_data.get("platform", "Instagram")
                theme = post_data.get("theme", "")
                aspect_ratio = post_data.get("aspect_ratio", "4:5")
                slides_count = post_data.get("slides", "1")
                chat_id = post_data.get("chat_id", "default")
                
                copy, slides_html, temp_user_files = generar_diseno_local(
                    platform, theme, aspect_ratio, slides_count, chat_id
                )
                
                files = ejecutar_render(slides_html, aspect_ratio)
                
                for u_path in temp_user_files:
                    try:
                        os.remove(u_path)
                    except Exception as e:
                        print(f"Error eliminando archivo temporal {u_path}: {e}")
                        
                response = {
                    "status": "success", 
                    "files": files,
                    "copy": copy
                }
                code = 200
            except Exception as e:
                import traceback
                traceback.print_exc()
                response = {"status": "error", "message": str(e)}
                code = 500
        else:
            try:
                files = ejecutar_render(post_data.get("slides", []), post_data.get("format", "4:5"))
                response = {"status": "success", "files": files}
                code = 200
            except Exception as e:
                response = {"status": "error", "message": str(e)}
                code = 500
            
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            slides = json.loads(sys.argv[1])
            ratio = sys.argv[2] if len(sys.argv) > 2 else "4:5"
            print(json.dumps({"files": ejecutar_render(slides, ratio)}))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
    else:
        server = HTTPServer(('0.0.0.0', 8000), RenderHandler)
        print("Servidor de Renderizado y Diseño escuchando en el puerto 8000...")
        server.serve_forever()