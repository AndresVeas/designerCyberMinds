import sys
import json
import os
import glob
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
import base64

# Definición del modelo Pydantic para estructurar la salida de Gemini
class DesignResponse(BaseModel):
    copy: str = Field(
        description="Texto final del post para la red social, optimizado con emojis y hashtags relevantes."
    )
    slides: List[str] = Field(
        description="Lista de páginas o slides del carrusel. Si se solicita generar N slides, esta lista DEBE contener exactamente N elementos. Cada elemento de esta lista DEBE ser un código HTML5 completo, independiente y válido (comenzando con <html> y terminando con </html>), con sus estilos <style> propios incluidos en el <head>."
    )

def ejecutar_render(slides, ratio, transparent=True):
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
            if transparent:
                page.evaluate("document.body.style.background = 'transparent';")
                page.evaluate("document.querySelectorAll('*').forEach(el => { if (el.classList.contains('slide-container') || el.id === 'slide-container') el.style.background = 'transparent'; })")
            
            output_path = f"/home/node/.n8n-files/slide_{i+1}.png"
            page.screenshot(path=output_path, full_page=False, omit_background=transparent)
            generated_files.append(output_path)
            
        browser.close()
    return generated_files

def generar_diseno_gemini(platform, theme, aspect_ratio, slides_count, chat_id, transparent=True):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurado en las variables de entorno.")
        
    client = genai.Client(api_key=api_key)
    contents = []
    
    # 1. Cargar imágenes de templates/estilos visuales
    templates_dir = "/home/node/.n8n-files/templates"
    template_files = glob.glob(os.path.join(templates_dir, "*"))
    template_parts = []
    for path in template_files:
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            try:
                mime_type = "image/png" if ext == ".png" else "image/jpeg"
                with open(path, "rb") as f:
                    data = f.read()
                template_parts.append(
                    types.Part.from_bytes(data=data, mime_type=mime_type)
                )
            except Exception as e:
                print(f"Error cargando template {path}: {e}")

    # 2. Cargar imágenes enviadas por el usuario para este chat_id
    user_inputs_dir = "/home/node/.n8n-files/user_inputs"
    user_files = glob.glob(os.path.join(user_inputs_dir, f"input_image_{chat_id}_*"))
    user_parts = []
    user_base64_strings = {}
    
    for path in user_files:
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            try:
                mime_type = "image/png" if ext == ".png" else "image/jpeg"
                with open(path, "rb") as f:
                    data = f.read()
                
                # Guardamos para el prompt multimodal
                user_parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
                
                # Convertimos a Base64 para el HTML injection
                b64_encoded = base64.b64encode(data).decode('utf-8')
                fname = os.path.basename(path)
                user_base64_strings[fname] = f"data:{mime_type};base64,{b64_encoded}"
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

    # 4. Construcción del Prompt Unificado (Sin sobreescrituras)
    prompt_text = f"""
    Eres un Director de Arte de vanguardia y Diseñador de Contenido Senior para marcas de Ciberseguridad de alto impacto (Estilo HorseCiab / CyberMinds).
    Tu objetivo es imitar y replicar con total fidelidad el estilo visual, la dirección de arte y el diseño gráfico de las imágenes de plantilla (Templates) que se te adjuntan.

    DATOS DEL POST:
    - Plataforma destino: {platform}
    - Tema central / Contexto: {theme}
    - Relación de Aspecto: {aspect_ratio}
    - Cantidad de Slides Planificados: {slides_count}

    REGLAS ESTRICTAS DE EXTRACCIÓN Y COPIA DE ESTILO VISUAL:
    1. Análisis de Plantillas (Templates):
       - Examina detalladamente las imágenes de plantilla adjuntas. Tu código HTML/CSS DEBE 'robar' (copiar y adaptar) exactamente sus elementos visuales.
       - Identifica y replica las fuentes tipográficas utilizadas (su nombre, peso y proporciones relativas para títulos y textos de lectura).
       - Identifica y replica la paleta de colores exacta: colores de fondo oscuros/negros, tonos de acento (cian neón, azul tecnológico), gradientes y colores de tarjetas.
       - Recrea las rejillas de fondo (grids), patrones tecnológicos, circuitos vectoriales, sombras, bordes translúcidos (glassmorphism) y detalles estéticos que observes.
       - Cada slide que generes debe verse como una continuación directa de esta misma serie de diseño gráfico.

    2. Composición Editorial y Prevención de Desbordes (Anti-Overflow):
       - Cada slide debe usar un contenedor maestro que ocupe todo el viewport sin desbordarse (`box-sizing: border-box; height: 100vh; width: 100vw; overflow: hidden; position: relative;`).
       - Mantén un margen de padding de seguridad amplio y elegante en los bordes del lienzo. Los textos y tarjetas NO deben tocar los bordes ni salirse de los límites físicos bajo ninguna circunstancia.
       - Organiza el contenido de forma estructurada, usando layouts limpios y asimétricos con Flexbox y Grid, tal como se muestra en las plantillas.
    """

    if template_parts:
        prompt_text += f"\n    A. IMÁGENES DE REFERENCIA DE DISEÑO (TEMPLATES) - {len(template_parts)} archivo(s):\n"
        prompt_text += "    Examina estas imágenes. Son tu única fuente de verdad para la paleta de colores, tipografía monumental, gradientes de fondo y estilos de tarjetas. El HTML generado debe clonar e integrarse con esta dirección de arte.\n"
    
    if user_parts:
        prompt_text += f"\n    B. IMÁGENES A INCLUIR EN EL DISEÑO:\n"
        prompt_text += "    Incrusta estas imágenes del usuario usando exclusivamente estas etiquetas <img src='...'> con sus data-uris correspondientes:\n"
        for fname, b64_str in user_base64_strings.items():
            prompt_text += f"       - Para {fname} usa exactamente: src='{b64_str}'\n"
    else:
        prompt_text += "\n    Nota: El usuario no ha subido imágenes específicas en esta ejecución. Genera el diseño usando maquetación e iconografía puramente vectorial.\n"

    if logo_svg_content:
        prompt_text += f"\n    C. INCLUSIÓN OBLIGATORIA DEL LOGO (CYBERMINDS):\n"
        prompt_text += "    Debes incrustar obligatoriamente este código SVG de forma inline dentro del encabezado (header) o pie de página (footer) de CADA slide:\n"
        prompt_text += f"    ```xml\n{logo_svg_content}\n```\n"
        prompt_text += "    REGLA DE COLOR DINÁMICO PARA EL LOGO: Como este logo es un isotipo vectorial nativo, analiza el color de fondo del slide actual y modifica directamente los atributos `fill` o `stroke` de sus paths internos en el HTML: usa blanco (`#ffffff`) si el fondo es oscuro, negro (`#000000`) si es muy claro, o su azul original si el contraste editorial se mantiene óptimo.\n"

    if transparent:
        prompt_text += """
    D. MANDATO DE FONDO TRANSPARENTE (EXTREMADAMENTE CRÍTICO):
       - El usuario solicitó un fondo transparente para poder superponer la imagen generada sobre otros fondos.
       - Por lo tanto, no debes establecer ningún color de fondo sólido, degradado o imagen de fondo en `html`, `body` o el contenedor principal (ej. `.slide-container`).
       - Configura obligatoriamente `background: transparent;` (o `background: none;`) en el contenedor maestro y en `body`.
       - Todos los elementos gráficos flotantes, tarjetas, textos e iconos HUD deben ser visibles pero estar sobre un lienzo completamente transparente.
        """

    # 5. Organizar el contenido para la API multimodal
    if template_parts:
        contents.append("IMÁGENES DE DISEÑO A SEGUIR (ESTILO):")
        contents.extend(template_parts)
    if user_parts:
        contents.append("IMÁGENES DEL USUARIO PARA INCLUIR EN EL POST:")
        contents.extend(user_parts)
        
    contents.append(prompt_text)

    system_instruction = f"Eres un diseñador visual de élite. Tu tarea obligatoria es generar exactamente {slides_count} slides en formato HTML/CSS. Cada elemento en la lista 'slides' debe ser un documento HTML5 completo y autónomo. El código HTML/CSS debe ser visualmente impactante, con tipografías de tamaño masivo, diseño asimétrico editorial, y debe funcionar perfectamente a pantalla completa dentro de un viewport sin barra de scroll. Evita a toda costa que el texto se traslape o se desborde del lienzo."

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DesignResponse,
            temperature=0.4,
            system_instruction=system_instruction
        )
    )

    result = json.loads(response.text)
    return result.get("copy", ""), result.get("slides", []), user_files

class RenderHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
        
        transparent = True
            
        if "theme" in post_data:
            try:
                platform = post_data.get("platform", "Instagram")
                theme = post_data.get("theme", "")
                aspect_ratio = post_data.get("aspect_ratio", "4:5")
                slides_count = post_data.get("slides", "1")
                chat_id = post_data.get("chat_id", "default")
                
                copy, slides_html, temp_user_files = generar_diseno_gemini(
                    platform, theme, aspect_ratio, slides_count, chat_id, transparent=transparent
                )
                
                files = ejecutar_render(slides_html, aspect_ratio, transparent=transparent)
                
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
                files = ejecutar_render(post_data.get("slides", []), post_data.get("format", "4:5"), transparent=transparent)
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