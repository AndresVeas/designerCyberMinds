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

# Definición del modelo Pydantic para estructurar la salida de Gemini
class DesignResponse(BaseModel):
    copy: str = Field(
        description="Texto final del post para la red social, optimizado con emojis y hashtags relevantes."
    )
    slides: List[str] = Field(
        description="Lista de páginas o slides del carrusel. Si se solicita generar N slides, esta lista DEBE contener exactamente N elementos. Cada elemento de esta lista DEBE ser un código HTML5 completo, independiente y válido (comenzando con <html> y terminando con </html>), con sus estilos <style> propios incluidos en el <head>."
    )

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

def generar_diseno_gemini(platform, theme, aspect_ratio, slides_count, chat_id):
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
    user_filenames = []
    for path in user_files:
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            try:
                mime_type = "image/png" if ext == ".png" else "image/jpeg"
                with open(path, "rb") as f:
                    data = f.read()
                user_parts.append(
                    types.Part.from_bytes(data=data, mime_type=mime_type)
                )
                user_filenames.append(os.path.basename(path))
            except Exception as e:
                print(f"Error cargando imagen de usuario {path}: {e}")

    prompt_text = f"""
    Eres un Director de Arte y Diseñador UI/UX Senior de élite especializado en marcas de Ciberseguridad, Tecnología y Diseño Premium de alto impacto.
    Debes generar el copy optimizado y la estructura visual de un carrusel de post en HTML/CSS de alto impacto basado en estos datos:
    - Red Social destino: {platform}
    - Tema/Contexto: {theme}
    - Relación de Aspecto Solicitada: {aspect_ratio}
    - Cantidad de Slides Planificados: {slides_count}

    Tenemos dos conjuntos de imágenes adjuntas en este mensaje:
    """

    if template_parts:
        prompt_text += f"\n    A. IMÁGENES DE REFERENCIA DE DISEÑO (TEMPLATES) - {len(template_parts)} archivo(s):\n"
        prompt_text += "    Úsalos como guía visual estricta para el estilo. Observa la composición tridimensional (3D), capas superpuestas, sombreados neón, texturas de circuitos electrónicos y bordes translúcidos con glassmorphism. El diseño generado DEBE ser igual de premium y tridimensional que estos ejemplos.\n"
    
    if user_parts:
        prompt_text += f"\n    B. IMÁGENES A INCLUIR EN EL DISEÑO - {len(user_parts)} archivo(s):\n"
        prompt_text += "    Estas imágenes del usuario deben integrarse visualmente dentro del lienzo. Para incluirlas en el HTML/CSS, usa los siguientes nombres de archivo exactos locales:\n"
        for fname in user_filenames:
            prompt_text += f"       - file:///home/node/.n8n-files/user_inputs/{fname}\n"
        prompt_text += "    Integra estas imágenes usando etiquetas <img> o divs de fondo con estilos decorativos 3D. Asegúrate de colocar una máscara oscura o gradiente transparente encima de ellas para garantizar el contraste del texto.\n"
    else:
        prompt_text += "\n    Nota: El usuario no ha subido imágenes en esta ejecución. Crea el diseño usando maquetación vectorial.\n"

    prompt_text += f"""
    Requerimientos Obligatorios de Dirección de Arte en HTML/CSS:
    1. Estructura y Fondo: Cada slide DEBE ocupar exactamente el 100% del lienzo: `width: 100vw; height: 100vh; margin:0; padding:0; overflow:hidden; position:relative; box-sizing:border-box; background:#020914;`. Usa fondos oscuros cyberpunk.
    2. Composición, Grillas y Distribución Espacial (CRÍTICO - EVITAR TRASLAPES):
       - EVITA TRASLAPES: Las tarjetas de texto, títulos, imágenes o iconos NO deben encimarse de forma ilegible. El texto nunca debe tapar elementos decorativos principales (como logos o escudos centrales).
       - Usa layouts modernos basados en Flexbox (`display: flex; flex-direction: column; justify-content: space-between; align-items: center;`) y Grid (`display: grid; grid-template-columns: repeat(2, 1fr);`) para organizar el contenido limpiamente.
       - Si usas posicionamiento absoluto para crear efectos de capas superpuestas, define coordenadas y z-index estrictos que garanticen una visualización ordenada.
       - Distribución Dinámica de Slides:
         * Genera exactamente {slides_count} slides HTML.
    3. Tipografía: Importa fuentes modernas desde Google Fonts como 'Syne', 'Orbitron' o 'Share Tech Mono', e 'Inter'.
    4. Tridimensionalidad y Detalles HUD: Aplica sombras intensas y bordes translúcidos con glassmorphism.
    """

    if template_parts:
        contents.append("IMÁGENES DE DISEÑO A SEGUIR (ESTILO):")
        contents.extend(template_parts)
    if user_parts:
        contents.append("IMÁGENES DEL USUARIO PARA INCLUIR EN EL POST:")
        contents.extend(user_parts)
        
    contents.append(prompt_text)

    system_instruction = f"Eres un diseñador visual de élite. Tu tarea obligatoria es generar exactamente {slides_count} slides en formato HTML/CSS. Cada elemento en la lista 'slides' debe ser un documento HTML5 completo y autónomo. El código HTML/CSS debe ser visualmente impactante, tridimensional, con efectos de capas superpuestas, sombreados neón intensos y glassmorphic, y debe funcionar perfectamente y a pantalla completa dentro de un viewport sin barra de scroll. Evita a toda costa que el texto se traslape con otros elementos."

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
        
        if "theme" in post_data:
            try:
                platform = post_data.get("platform", "Instagram")
                theme = post_data.get("theme", "")
                aspect_ratio = post_data.get("aspect_ratio", "4:5")
                slides_count = post_data.get("slides", "1")
                chat_id = post_data.get("chat_id", "default")
                
                copy, slides_html, temp_user_files = generar_diseno_gemini(
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