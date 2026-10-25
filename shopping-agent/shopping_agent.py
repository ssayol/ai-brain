"""
Shopping Agent para seguimiento de productos de fotografía
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright

# Configuración de tiendas: nombre -> plantilla de URL de búsqueda
tiendas_fotografia = {
    "FotoRuano": "https://www.fotoruanopro.com/?s={query}&controller=search",
    "Fotografiarte": "https://www.fotografiarte.com/catalogsearch/result/?q={query}",
    "Duke Fotografía": "https://www.duke.es/catalogsearch/result/?q={query}",
    "Casanova Foto": "https://www.casanovafoto.com/catalogsearch/result/?q={query}",
    "FotoK": "https://www.fotok.es/catalogsearch/result/?q={query}"
}

RUTA_LOGS = r"c:\OneDrive Personal\OneDrive\Claude\Gmail\AI-Brain\shopping-agent\logs"

tiendas_generales = {
    "Amazon España": "https://www.amazon.es",
    "PcComponentes": "https://www.pccomponentes.com",
    "El Corte Inglés": "https://www.elcorteingles.es",
    "MediaMarkt": "https://www.mediamarkt.es",
    "Fnac": "https://www.fnac.es",
    "Worten": "https://www.worten.es",
    "TradeInn": "https://www.tradeinn.com"
}

class ShoppingAgent:
    def __init__(self):
        """Inicializa el Shopping Agent"""
        self.db_path = "c:\\OneDrive Personal\\OneDrive\\Claude\\Gmail\\AI-Brain\\shopping-agent\\data\\prices.db"
        self.init_database()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def init_database(self):
        """Inicializa la base de datos SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto TEXT NOT NULL,
                tienda TEXT NOT NULL,
                precio REAL NOT NULL,
                url TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def parsear_precio(self, texto: str) -> Optional[float]:
        """Convierte un texto de precio a float"""
        import re
        if not texto:
            return None
        texto = texto.replace('\xa0', ' ')
        m = re.search(r'\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:[.,]\d+)?', texto)
        if not m:
            return None
        num = m.group(0)
        if ',' in num and '.' in num:
            num = num.replace('.', '').replace(',', '.')
        elif ',' in num:
            num = num.replace(',', '.')
        try:
            return float(num)
        except ValueError:
            return None

    def extraer_productos(self, page, nombre_tienda: str, url_base: str) -> List[Dict]:
        """Extrae productos probando varias estrategias de selectores"""
        resultados = []
        estrategias = [
            (".product-miniature", ".product-title a, h2 a"),
            (".product-item", ".product-item-link, .product-name a"),
            ("h2 a", None),
        ]
        for contenedor, sel_nombre in estrategias:
            try:
                items = page.query_selector_all(contenedor)
                for item in items[:5]:
                    try:
                        el_nombre = item.query_selector(sel_nombre) if sel_nombre else item
                        if not el_nombre:
                            continue
                        nombre = el_nombre.inner_text().strip()
                        if len(nombre) < 3:
                            continue
                        el_precio = item.query_selector(".price, .product-price, .amount")
                        if not el_precio:
                            continue
                        precio = self.parsear_precio(el_precio.inner_text())
                        if precio is None:
                            continue
                        el_link = item.query_selector('a[href]')
                        url = ""
                        if el_link:
                            url = el_link.get_attribute('href') or ""
                            if url and not url.startswith('http'):
                                url = url_base + url
                        resultados.append({
                            "producto": nombre,
                            "tienda": nombre_tienda,
                            "precio": precio,
                            "url": url,
                            "fecha": datetime.now().isoformat()
                        })
                    except Exception:
                        continue
                if resultados:
                    break
            except Exception:
                continue
        return resultados

    def buscar_producto(self, producto: str) -> List[Dict]:
        """Busca un producto en las tiendas configuradas"""
        resultados = []
        query = producto.replace(' ', '+')

        for nombre_tienda, url_plantilla in tiendas_fotografia.items():
            print(f"🔍 Buscando {producto} en {nombre_tienda}...")
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                    search_url = url_plantilla.format(query=query)
                    page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    url_base = search_url.split('?')[0]
                    productos = self.extraer_productos(page, nombre_tienda, url_base)
                    if productos:
                        print(f"   ✅ {len(productos)} productos encontrados")
                        for prod in productos:
                            self.guardar_precio(prod["producto"], prod["tienda"], prod["precio"], prod["url"])
                        resultados.extend(productos)
                    else:
                        archivo_log = f"debug_{nombre_tienda.replace(' ', '_').replace('í', 'i')}.html"
                        ruta_log = RUTA_LOGS + "\\" + archivo_log
                        print(f"   ⚠️ Sin resultados - HTML guardado en: {ruta_log}")
                        try:
                            with open(ruta_log, "w", encoding="utf-8") as f:
                                f.write(page.content())
                        except Exception as e:
                            print(f"   ⚠️ No se pudo guardar el HTML: {e}")
                    browser.close()

            except Exception as e:
                print(f"   ❌ Error buscando en {nombre_tienda}: {e}")
                continue

        return resultados
    
    def guardar_precio(self, producto: str, tienda: str, precio: float, url: str):
        """Guarda el precio en la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO price_history (producto, tienda, precio, url)
            VALUES (?, ?, ?, ?)
        ''', (producto, tienda, precio, url))
        conn.commit()
        conn.close()
    
    def get_historico_precios(self, producto: str) -> pd.DataFrame:
        """Obtiene el historico de precios para un producto"""
        conn = sqlite3.connect(self.db_path)
        query = """
        SELECT * FROM price_history 
        WHERE producto LIKE ?
        ORDER BY fecha DESC
        """
        df = pd.read_sql_query(query, conn, params=[f"%{producto}%"])
        conn.close()
        return df
    
    def analizar_recomendacion_compra(self, producto: str) -> Dict:
        """Analiza si es buen momento para comprar"""
        df = self.get_historico_precios(producto)
        if df.empty:
            return {"error": "No hay datos históricos para este producto"}
        
        precio_actual = df['precio'].iloc[0]
        precio_medio_90dias = df['precio'].head(30).mean()
        
        return {
            "producto": producto,
            "precio_actual": precio_actual,
            "precio_medio_90dias": precio_medio_90dias,
            "diferencia": precio_actual - precio_medio_90dias,
            "porcentaje": ((precio_actual - precio_medio_90dias) / precio_medio_90dias) * 100,
            "recomendacion": "Buen momento para comprar" if precio_actual < precio_medio_90dias else "Esperar a mejores precios"
        }


# Ejemplo de uso
def main():
    agent = ShoppingAgent()
    
    # Buscar Fuji X-E5 con XF27
    print("🚀 Buscando Fuji X-E5 con objetivo XF27")
    resultados = agent.buscar_producto("Fuji X-E5 XF27")
    
    if resultados:
        print(f"\n✅ Encontrados {len(resultados)} productos")
        for resultado in resultados:
            print(f"- {resultado['producto']}")
            print(f"  {resultado['precio']}€ en {resultado['tienda']}")
            print(f"  {resultado['url']}")
            print(f"  Fecha: {resultado['fecha']}")
        
        # Analizar si es buen momento para comprar
        analisis = agent.analizar_recomendacion_compra("Fuji X-E5")
        if "error" not in analisis:
            print(f"\n📊 Análisis de compra para {analisis['producto']}")
            print(f"Precio actual: {analisis['precio_actual']}€")
            print(f"Precio medio 90 días: {analisis['precio_medio_90dias']:.2f}€")
            print(f"Diferencia: {analisis['diferencia']:.2f}€ ({analisis['porcentaje']:.1f}%)")
            print(f"Recomendación: {analisis['recomendacion']}")
    else:
        print("❌ No se encontraron productos")

if __name__ == "__main__":
    main()