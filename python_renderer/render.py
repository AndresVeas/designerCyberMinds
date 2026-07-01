import sys
import json
import os
import glob
import random
import requests
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Literal
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

def obtener_estado_templates(templates_dir):
    templates_state = {}
    if not os.path.exists(templates_dir):
        return templates_state
    for path in glob.glob(os.path.join(templates_dir, "*")):
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            try:
                stat = os.stat(path)
                templates_state[os.path.basename(path)] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime
                }
            except Exception as e:
                print(f"Error obteniendo estado de {path}: {e}")
    return templates_state

def actualizar_prompts_estilo(client, templates_dir, shared_dir, templates_state):
    print("El estado de templates ha cambiado o faltan prompts de estilo. Regenerando prompts con Gemini...")
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
                print(f"Error cargando template para regeneración {path}: {e}")

    if not template_parts:
        print("No se encontraron imágenes en la carpeta templates. Creando prompts vacíos por defecto.")
        with open(os.path.join(shared_dir, "style.txt"), "w", encoding="utf-8") as f:
            f.write("abstract dark cybersecurity background, professional design, no text")
        with open(os.path.join(shared_dir, "fontTemplate.txt"), "w", encoding="utf-8") as f:
            f.write("Estilo editorial moderno, tipografía de tamaño masivo en títulos, fuentes limpias como Inter.")
        return

    # 1. Generar style.txt (solo el fondo)
    print("Generando style.txt...")
    prompt_style = (
        "Analiza estas plantillas de diseño. Describe en inglés y con detalle el estilo visual de fondo y la atmósfera "
        "(colores principales, texturas tecnológicas, rejillas de fondo, circuitos, iluminación, degradados oscuros, etc.) "
        "en un prompt optimizado para un generador de imágenes por IA (como Perchance/Stable Diffusion). "
        "Este prompt debe enfocarse ÚNICAMENTE en el fondo (background). NO debe hacer ninguna mención a textos, tipografías, "
        "cajas de texto, layouts, marcos ni rostros humanos. El resultado final debe ser estrictamente un prompt directo de "
        "un solo párrafo en inglés."
    )
    
    try:
        try:
            resp_style = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=template_parts + [prompt_style],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    system_instruction="Eres un ingeniero de prompts experto en generación de fondos abstractos y de ciberseguridad."
                )
            )
        except Exception as fe:
            print(f"Error con gemini-2.5-flash al generar style.txt: {fe}. Probando fallback con gemini-2.0-flash...")
            resp_style = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=template_parts + [prompt_style],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    system_instruction="Eres un ingeniero de prompts experto en generación de fondos abstractos y de ciberseguridad."
                )
            )
        style_content = resp_style.text.strip()
        with open(os.path.join(shared_dir, "style.txt"), "w", encoding="utf-8") as f:
            f.write(style_content)
        print("style.txt guardado con éxito.")
    except Exception as e:
        print(f"Error generando style.txt: {e}")

    # 2. Generar fontTemplate.txt (tipografía, tarjetas, maquetación visual)
    print("Generando fontTemplate.txt...")
    prompt_font = (
        "Analiza estas plantillas de diseño. Extrae las directrices visuales estrictamente relacionadas con las fuentes, "
        "tipografías (nombres de Google Fonts preferidas, tamaños de títulos monumentales en rem/px/vw, colores y pesos tipográficos), "
        "el estilo visual de las tarjetas o recuadros de texto (bordes, transparencias, sombreados HUD, glassmorphism) "
        "y la composición editorial/distribución de textos en los slides. Ignora por completo los fondos o imágenes de fondo.\n\n"
        "REGLA CRÍTICA DE CONTENIDO:\n"
        "- Esta guía NO debe incluir los textos o temáticas de las imágenes de ejemplo (como hackeos, nombres de países, etc.) como contenido obligatorio. El texto final será provisto dinámicamente.\n"
        "- En cualquier ejemplo de maquetación HTML/CSS que escribas, usa marcadores abstractos como '[TITULO_POST]', '[DESCRIPCION_TARJETA]', '[ETIQUETA]' o texto Lorem Ipsum.\n"
        "- El resultado debe ser una guía técnica de maquetación en español para que se puedan replicar los estilos visuales en cualquier página web."
    )
    
    try:
        try:
            resp_font = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=template_parts + [prompt_font],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    system_instruction="Eres un director de arte digital y maquetador CSS experto."
                )
            )
        except Exception as fe:
            print(f"Error con gemini-2.5-flash al generar fontTemplate.txt: {fe}. Probando fallback con gemini-2.0-flash...")
            resp_font = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=template_parts + [prompt_font],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    system_instruction="Eres un director de arte digital y maquetador CSS experto."
                )
            )
        font_content = resp_font.text.strip()
        with open(os.path.join(shared_dir, "fontTemplate.txt"), "w", encoding="utf-8") as f:
            f.write(font_content)
        print("fontTemplate.txt guardado con éxito.")
    except Exception as e:
        print(f"Error generando fontTemplate.txt: {e}")

    # Guardar estado actual
    with open(os.path.join(shared_dir, "templates_state.json"), "w", encoding="utf-8") as f:
        json.dump(templates_state, f, indent=4)
    print("templates_state.json actualizado.")

def generar_fondo_huggingface(theme: str, aspect_ratio: str, style_prompt: str, chat_id: str, index: int) -> str:
    """
    Genera un fondo usando la API de Hugging Face y lo guarda como un archivo PNG local en el directorio compartido.
    Mapea la relación de aspecto a la resolución recomendada para FLUX.
    """
    shared_dir = "/home/node/.n8n-files"
    output_filename = f"background_{chat_id}_{index}.png"
    output_path = os.path.join(shared_dir, output_filename)
    
    # Obtener el token de Hugging Face
    hf_token = os.environ.get("HUGGING_FACE")
    if not hf_token:
        print("Error: HUGGING_FACE token no configurado en las variables de entorno.")
        return None
        
    # Mapeo de resolución para FLUX (normalmente prefiere múltiplos de 8 y tamaño cercano a 1MP)
    dims = {
        '1:1': (1024, 1024),
        '4:5': (832, 1040),
        '16:9': (1024, 576),
        '9:16': (576, 1024)
    }
    width, height = dims.get(aspect_ratio, (832, 1040))
    
    # Construir el prompt concatenando el estilo guardado en caché y el tema
    prompt = f"{style_prompt}. Theme: {theme}, clean design, professional lighting, digital art, high quality"
    print(f"Generando fondo con Hugging Face. Prompt: {prompt}")
    print(f"Dimensiones asignadas para {aspect_ratio}: {width}x{height}")
    
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=hf_token)
        
        # Generar imagen usando el modelo FLUX.1-schnell
        image = client.text_to_image(
            prompt=prompt,
            negative_prompt="text, words, letters, logos, faces, human, people, deformed, signature, watermark",
            width=width,
            height=height,
            model="black-forest-labs/FLUX.1-schnell"
        )
        
        # Guardar imagen devuelta
        image.save(output_path)
        print(f"Fondo de Hugging Face guardado en {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error generando fondo en Hugging Face: {e}")
        return None

def generar_diseno_gemini(platform, theme, aspect_ratio, slides_count, chat_id):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurado en las variables de entorno.")
        
    client = genai.Client(api_key=api_key)
    
    # 1. Gestión del Caching de Plantillas (Templates)
    templates_dir = "/home/node/.n8n-files/templates"
    shared_dir = "/home/node/.n8n-files"
    current_state = obtener_estado_templates(templates_dir)
    
    state_file = os.path.join(shared_dir, "templates_state.json")
    style_file = os.path.join(shared_dir, "style.txt")
    font_file = os.path.join(shared_dir, "fontTemplate.txt")
    
    needs_regen = True
    if os.path.exists(state_file) and os.path.exists(style_file) and os.path.exists(font_file):
        try:
            with open(state_file, "r") as f:
                stored_state = json.load(f)
            if stored_state == current_state:
                needs_regen = False
        except Exception:
            pass
            
    if needs_regen:
        actualizar_prompts_estilo(client, templates_dir, shared_dir, current_state)
        
    # Leer prompts guardados en caché
    with open(style_file, "r", encoding="utf-8") as f:
        style_prompt = f.read().strip()
    with open(font_file, "r", encoding="utf-8") as f:
        font_instruction = f.read().strip()
        
    # 2. Generación de los Fondos de Hugging Face (se genera uno para cada diapositiva y se guardan localmente)
    background_files = []
    try:
        count_val = int(slides_count)
    except Exception:
        count_val = 1
        
    for i in range(1, count_val + 1):
        bg_file = generar_fondo_huggingface(theme, aspect_ratio, style_prompt, chat_id, i)
        if bg_file:
            background_files.append(bg_file)
        
    # 3. Cargar imágenes enviadas por el usuario para este chat_id
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
                user_parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
                b64_encoded = base64.b64encode(data).decode('utf-8')
                fname = os.path.basename(path)
                user_base64_strings[fname] = f"data:{mime_type};base64,{b64_encoded}"
            except Exception as e:
                print(f"Error cargando imagen de usuario {path}: {e}")

    # 4. Cargar el Logo SVG dinámico de CyberMinds
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

    # 5. Construcción del Prompt para Gemini
    prompt_text = f"""
    Eres un Director de Arte de vanguardia y Diseñador de Contenido Senior para marcas de Ciberseguridad de alto impacto (Estilo HorseCiab / CyberMinds).
    Tu objetivo es maquetar exactamente {slides_count} slides de carrusel en formato HTML/CSS que tengan una alta fuerza editorial, tipografía masiva y diseño premium de última generación.
    
    DATOS DEL POST:
    - Plataforma destino: {platform}
    - Tema central / Contexto (Usa esto para redactar todo el texto de los slides): {theme}
    - Relación de Aspecto: {aspect_ratio}
    - Cantidad de Slides Planificados: {slides_count}
    
    GUÍA DE ESTILO VISUAL DE FUENTES Y LAYOUT (Sigue estas instrucciones estrictamente):
    {font_instruction}
    
    REGLAS OBLIGATORIAS DE DISEÑO PREMIUM (ESTILO HUD / CYBERPUNK / HIGH-TECH):
    - El diseño debe verse sumamente profesional, tecnológico y editorial. No te limites a centrar el texto de forma aburrida.
    - Contraste Inteligente en Lienzo Transparente: Como el fondo es transparente y se colocará sobre una imagen de Perchance, el texto blanco o claro debe ser perfectamente legible. Usa siempre sombras neón en los títulos (`text-shadow: 0 0 8px rgba(0, 229, 255, 0.6), 0 0 15px rgba(0, 0, 0, 0.8);`) y coloca los bloques de información dentro de tarjetas con fondos traslúcidos oscuros (`rgba(10, 15, 25, 0.75)` o `rgba(0, 0, 0, 0.8)`), con bordes neón de 1px (`border: 1px solid rgba(0, 229, 255, 0.2);`) y bordes laterales resaltados de 4px.
    - Estructura y Elementos Decorativos HUD:
      * Agrega pequeños detalles estéticos de adorno de alta tecnología, como pseudo-elementos con marcos angulares en las esquinas, cruces de mira (crosshairs), pequeñas etiquetas técnicas como `[SEC_STATUS: COMPLIANT]`, `SYS_BOOT: OK`, `[LEVEL_01]`.
      * Usa líneas delgadas de separación de 1px con degradados de neón.
      * Envuelve números o palabras clave con corchetes tipográficos decorativos (`[01]`, `[REQUERIDO]`).
    - Composición Asimétrica y Dinámica:
      * Varía el layout entre los slides para que sea visualmente estimulante.
      * Usa layouts asimétricos con columnas, tarjetas flotantes con diferentes anchos y alturas, y cajas tipográficas staggered (escalonadas).
      * Deja amplios márgenes internos (padding de seguridad) para evitar que cualquier elemento toque los bordes físicos.
    
    DIRECTRIZ DE CONTENIDO CRÍTICA:
    - El tema a desarrollar en todos los slides es exclusivamente: "{theme}".
    - La "GUÍA DE ESTILO VISUAL DE FUENTES Y LAYOUT" anterior contiene ejemplos visuales con textos que NO debes copiar. Debes ignorar por completo cualquier referencia conceptual o texto de ejemplo que venga dentro de esa guía (como temas de hackeos de Argentina, historias clínicas, etc.) y reemplazarlos por contenido original basado en el tema de esta ejecución: "{theme}".
    
    MANDATO DE FONDO TRANSPARENTE:
    - No establezcas ningún color de fondo sólido, degradado o imagen en `html`, `body` o el contenedor principal.
    - Configura obligatoriamente `background: transparent;` en el contenedor maestro y en `body`.
    - Todos los elementos gráficos, tarjetas, textos e iconos HUD deben ser visibles pero estar sobre un lienzo transparente.
    """

    if user_parts:
        prompt_text += f"\n    A. IMÁGENES A INCLUIR EN EL DISEÑO:\n"
        prompt_text += "    Incrusta estas imágenes del usuario usando exclusivamente estas etiquetas <img src='...'> con sus data-uris correspondientes:\n"
        for fname, b64_str in user_base64_strings.items():
            prompt_text += f"       - Para {fname} usa exactamente: src='{b64_str}'\n"
    else:
        prompt_text += "\n    Nota: El usuario no ha subido imágenes específicas en esta ejecución. Genera el diseño usando maquetación e iconografía puramente vectorial.\n"

    if logo_svg_content:
        prompt_text += f"\n    B. INCLUSIÓN OBLIGATORIA DEL LOGO (CYBERMINDS):\n"
        prompt_text += "    Debes incrustar obligatoriamente este código SVG de forma inline dentro del encabezado (header) o pie de página (footer) de CADA slide:\n"
        prompt_text += f"    ```xml\n{logo_svg_content}\n```\n"
        prompt_text += "    REGLA DE COLOR DINÁMICO PARA EL LOGO: Analiza el color del slide actual y modifica directamente los atributos `fill` o `stroke` de sus paths internos en el HTML: usa blanco (`#ffffff`) si el fondo es oscuro, negro (`#000000`) si es muy claro, o su azul original si el contraste editorial se mantiene óptimo.\n"

    contents = []
    if user_parts:
        contents.append("IMÁGENES DEL USUARIO PARA INCLUIR EN EL POST:")
        contents.extend(user_parts)
    contents.append(prompt_text)

    system_instruction = f"Eres un diseñador visual de élite especializado en interfaces HUD de ciberseguridad, estética cyberpunk y diseño de contenido premium. Tu tarea obligatoria es generar exactamente {slides_count} slides en formato HTML/CSS de altísima calidad visual. Cada slide en 'slides' debe ser un documento HTML5 completo, responsivo y autónomo, listo para pantalla completa (sin barras de scroll). Utiliza elementos gráficos HUD ricos (marcos, esquinas recortadas, resplandores neón, tarjetas glassmorphic oscuras y detalles técnicos) para lograr un producto de apariencia sumamente premium."

    try:
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
    except Exception as fe:
        print(f"Error con gemini-2.5-flash al generar slides: {fe}. Probando fallback con gemini-2.0-flash...")
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DesignResponse,
                temperature=0.4,
                system_instruction=system_instruction
            )
        )

    result = json.loads(response.text)
    return result.get("copy", ""), result.get("slides", []), user_files, background_files


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
                
                # Forzamos transparent=True internamente para la generación de diseño
                copy, slides_html, temp_user_files, background_files = generar_diseno_gemini(
                    platform, theme, aspect_ratio, slides_count, chat_id
                )
                
                # Forzamos transparent=True en el renderizador Playwright
                files = ejecutar_render(slides_html, aspect_ratio, transparent=True)
                
                for u_path in temp_user_files:
                    try:
                        os.remove(u_path)
                    except Exception as e:
                        print(f"Error eliminando archivo temporal {u_path}: {e}")
                        
                response = {
                    "status": "success", 
                    "files": files + background_files,
                    "backgrounds": background_files,
                    "background": background_files[0] if background_files else None,
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
                transparent = post_data.get("transparent", True)
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