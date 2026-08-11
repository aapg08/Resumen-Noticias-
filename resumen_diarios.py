import requests
import re
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import yfinance as yf
import json
import html
import os
from dotenv import load_dotenv

# ==========================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# ==========================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# # Cliente configurado para los servidores de GitHub Models
# client = OpenAI(
#     base_url="https://models.inference.ai.azure.com",
#     api_key=GITHUB_TOKEN,
# )

# ==========================================
# 2. EXTRACCIÓN DE NOTICIAS
# ==========================================

def obtener_indicadores_emol_exactos():
  """Extrae los valores EXACTOS de la portada de Emol (Dólar interbancario, UF, UTM, IPC)"""
  indicadores = []
  url_movil = "https://www.emol.com/movil/Economia/"

  try:
    resp = requests.get(url_movil, headers=HEADERS, timeout=8)
    if resp.status_code == 200:
      soup = BeautifulSoup(resp.content, "html.parser")
      texto = soup.get_text(separator=" ", strip=True)

      # 1. Dólar Interbancario (Ej: Dolar interbancario = 918,95)
      dolar_m = re.search(
          r"Dolar\s+interbancario\s*=\s*[\d\.,]+", texto, re.IGNORECASE
      )
      if dolar_m:
        indicadores.append(dolar_m.group(0))

      # 2. UF (Ej: UF = 40.846,11)
      uf_m = re.search(r"UF\s*=\s*[\d\.,]+", texto, re.IGNORECASE)
      if uf_m:
        indicadores.append(uf_m.group(0))

      # 3. UTM (Ej: UTM = 71.649)
      utm_m = re.search(r"UTM\s*=\s*[\d\.,]+", texto, re.IGNORECASE)
      if utm_m:
        indicadores.append(utm_m.group(0))

      # 4. IPC (Ej: IPC = 0,10%)
      ipc_m = re.search(r"IPC\s*=\s*[\d\.,%]+", texto, re.IGNORECASE)
      if ipc_m:
        indicadores.append(ipc_m.group(0))

  except Exception as e:
    print(f"Error cargando indicadores de Emol: {e}")

  return indicadores


def obtener_datos_emol():
    url = "https://www.emol.com/economia/"
    noticias = []
    
    # 1. Obtener indicadores precisos
    indicadores = obtener_indicadores_emol_exactos()

    # 2. Obtener noticias de Emol
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            bloques = soup.find_all(['div', 'li', 'article'])
            
            palabras_basura = [
                "migración", "migrada", "contraseña", "iniciar sesión", 
                "términos", "privacidad", "comentario", "recomendados", 
                "comunidad", "suscripción", "registrarse", "olvidaste"
            ]

            for bloque in bloques:
                titulo_elem = bloque.find(['h1', 'h2', 'h3', 'h4', 'a'])
                if not titulo_elem:
                    continue
                
                titulo = titulo_elem.get_text(strip=True)
                
                if len(titulo) < 25 or titulo in str(noticias):
                    continue
                
                if any(basura in titulo.lower() for basura in palabras_basura):
                    continue

                bajada_elem = bloque.find(['p', 'span'])
                bajada = bajada_elem.get_text(strip=True) if bajada_elem else ""
                
                if len(bajada) > 15 and not any(b in bajada.lower() for b in palabras_basura):
                    noticias.append(f"{titulo} -> {bajada}")
                else:
                    noticias.append(titulo)

    except Exception as e:
        print(f"Error extrayendo Emol: {e}")
        
    resumen_noticias = list(dict.fromkeys(noticias))
    
    return indicadores, resumen_noticias[:15]

def obtener_titulares_df():
    url = "https://www.df.cl/"
    noticias = []
    
    palabras_basura = [
        "click acá", "ir directamente", "suscríbete", "iniciar sesión", 
        "suscripción", "diario financiero", "términos", "privacidad", 
        "boletines", "ingresar", "edición impresa", "paper digital",
        "newsletter", "ver más", "podcast", "escuchar"
    ]

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Buscamos todos los artículos o bloques de noticias en el cuerpo
            bloques = soup.find_all(['article', 'div'])

            for bloque in bloques:
                # Buscamos el título dentro del bloque
                titulo_elem = bloque.find(['h2', 'h3', 'h4', 'a'])
                if not titulo_elem:
                    continue
                
                titulo = titulo_elem.get_text(strip=True)
                
                # Filtros de longitud y duplicados
                if len(titulo) < 20 or titulo in str(noticias):
                    continue
                
                # Descartar basura
                if any(basura in titulo.lower() for basura in palabras_basura):
                    continue

                # Buscamos la bajada / párrafo explicativo de la noticia
                bajada_elem = bloque.find(['p', 'span'])
                bajada = bajada_elem.get_text(strip=True) if bajada_elem else ""
                
                # Si la bajada aporta valor y no es basura
                if len(bajada) > 20 and not any(b in bajada.lower() for b in palabras_basura):
                    noticias.append(f"{titulo} -> {bajada}")
                else:
                    noticias.append(titulo)

    except Exception as e:
        print(f"Error raspando DF: {e}")

    # Eliminamos duplicados manteniendo el orden
    noticias_limpias = list(dict.fromkeys(noticias))
    
    # Devolvemos hasta 20 noticias bien detalladas para Gemini
    return noticias_limpias[:20]

def obtener_ipsa_exacto():
  """Extrae los PUNTOS exactos del IPSA directamente desde el HTML de df.cl"""
  try:
    # 1. Petición directa a la portada de Diario Financiero
    url_df = "https://www.df.cl/"
    resp = requests.get(url_df, headers=HEADERS, timeout=8)
    if resp.status_code == 200:
      soup = BeautifulSoup(resp.content, "html.parser")
      texto = soup.get_text(separator=" ", strip=True)

      # Buscamos la etiqueta IPSA y capturamos el valor en puntos
      # Ejemplo en el texto: "IPSA 11.256,28" o "IPSA: 11.256,28" o "IPSA 11256,28"
      match = re.search(
          r"IPSA\s*[:\s]*([\d\.,]{5,10})", texto, re.IGNORECASE
      )
      if match:
        val_str = match.group(1).strip()
        # Verificación básica para asegurar que capturamos un número de puntos válido
        if len(val_str) >= 5:
          return f"IPSA (Chile) = {val_str} puntos"

      # Búsqueda alternativa por contenedores de Market Data en DF
      for elem in soup.find_all(["div", "span", "td", "a"]):
        txt = elem.get_text(strip=True)
        if "IPSA" in txt and len(txt) < 30:
          num = re.search(r"[\d\.,]{5,10}", txt)
          if num:
            return f"IPSA (Chile) = {num.group(0)} puntos"

  except Exception as e:
    print(f"Error consultando IPSA en DF: {e}")

  # 2. Respaldo directo vía Yahoo Finance usando el ticker oficial de la Bolsa de Santiago (.SN)
  try:

    df = yf.download("^IPSA", period="5d", progress=False)
    if df.empty:
      df = yf.download("SP_IPSA.SN", period="5d", progress=False)

    if not df.empty:
      val = df["Close"].iloc[-1]
      if hasattr(val, "item"):
        val = val.item()
      val_fmt = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
      return f"IPSA (Chile) = {val_fmt} puntos"
  except Exception:
    pass

  return "IPSA (Chile) = No disponible"

def obtener_mercados_automatico():
  """Obtiene IPSA y S&P 500 de forma robusta"""
  mercados = []

  # 1. Obtener IPSA mediante Google Finance
  ipsa_val = obtener_ipsa_exacto()
  mercados.append(ipsa_val)

  # 2. Obtener S&P 500 mediante yfinance
  try:
    df_sp = yf.download("^GSPC", period="5d", progress=False)
    if not df_sp.empty:
      val_sp = df_sp["Close"].iloc[-1]
      if hasattr(val_sp, "item"):
        val_sp = val_sp.item()
      fecha_sp = df_sp.index[-1].strftime("%d/%m/%Y")
      sp_fmt = f"{val_sp:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
      mercados.append(f"S&P 500 (EE.UU.) = {sp_fmt} (al {fecha_sp})")
    else:
      mercados.append("S&P 500 (EE.UU.) = No disponible")
  except Exception as e:
    print(f"Error al obtener S&P 500: {e}")
    mercados.append("S&P 500 (EE.UU.) = Error")

  return mercados

# ==========================================
# 3. GENERACIÓN DEL RESUMEN
# ==========================================
def generar_resumen(indicadores, emol, df):
  texto_indicadores = "INDICADORES ECONÓMICOS Y MERCADOS HOY:\n" + "\n".join(
      f"• {i}" for i in indicadores if i
  )
  texto_noticias = (
      "NOTICIAS EMOL ECONOMÍA:\n"
      + "\n".join(f"- {n}" for n in emol if n)
      + "\n\nNOTICIAS DIARIO FINANCIERO:\n"
      + "\n".join(f"- {n}" for n in df if n)
  )

  prompt = f"""
    Actúa como un profesor de finanzas. Resume estas noticias e indicadores de hoy para un estudiante universitario que prepara sus controles del ramo de finanzas:

    {texto_indicadores}

    {texto_noticias}

    Formato estricto para Telegram:
    📌 *RESUMEN DE ECONOMÍA*

    📊 *INDICADORES Y MERCADOS CLAVE:*
    (Muestra las cifras exactas entregadas de Dólar Interbancario, UF, UTM, IPC, IPSA y S&P 500)

    🔹 *1. Conceptos y Temas Clave:*
    (Resume en 9-10 puntos con lenguaje económico los temas más relevantes, sé específico pero también agrega detalles necesarios para poder comprender las noticias y así memorizarlas de mejor manera)

    💡 *2. Preguntas Tipo Control:*
    (Formula 2 o 3 preguntas conceptuales de opción múltiple basadas en los hechos de hoy. Dame las respuestas correctas al final)
    """

  url = "https://api.groq.com/openai/v1/chat/completions"
  headers = {
      "Authorization": f"Bearer {GROQ_API_KEY}",
      "Content-Type": "application/json",
  }
  payload = {
      "model": "llama-3.3-70b-versatile",
      "messages": [{"role": "user", "content": prompt}],
      "temperature": 0.3,
  }

  res = requests.post(
      url, headers=headers, data=json.dumps(payload), timeout=30
  )
  return res.json()["choices"][0]["message"]["content"]

# ==========================================
# 4. ENVÍO A TELEGRAM
# ==========================================
def enviar_telegram(mensaje):
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

  # Convertimos el formato Markdown basico (*texto*) a HTML (<b>texto</b>)
  # para que Telegram no rebote por caracteres especiales
  mensaje_html = mensaje.replace("**", "<b>").replace("**", "</b>")

  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": mensaje,
      "parse_mode": "Markdown",
  }

  res = requests.post(url, json=payload, timeout=10)

  if res.status_code == 200:
    print("✅ Reporte enviado exitosamente a Telegram con formato!")
  else:
    # Reintento de seguridad en texto plano
    payload.pop("parse_mode", None)
    res_retry = requests.post(url, json=payload, timeout=10)
    if res_retry.status_code == 200:
      print("⚠️ Enviado a Telegram (en texto plano).")
    else:
      print(f"❌ Error al enviar a Telegram: {res_retry.text}")

# ==========================================
# 5. EJECUCIÓN
# ==========================================
if __name__ == "__main__":
    print("Obteniendo noticias e indicadores de Emol...")
    ind_emol, e = obtener_datos_emol()

    print("Obteniendo datos bursátiles (IPSA / S&P 500)...")
    bolsa = obtener_mercados_automatico()

    # Unimos todos los indicadores
    indicadores_completos = ind_emol + bolsa

    print("Obteniendo noticias de Diario Financiero...")
    d = obtener_titulares_df()

    print("Generando resumen...")
    r = generar_resumen(indicadores_completos, e, d)

    print("Enviando reporte a tu celular...")
    enviar_telegram(r)