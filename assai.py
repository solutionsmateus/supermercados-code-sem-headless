# assai.py — pronto para rodar em headless no GitHub Actions e salvar em OUTPUT_DIR

import time
import requests
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import re
import os
import sys

# =========================
# CONFIGURAÇÕES / CONSTANTES
# =========================

# Lê OUTPUT_DIR do ambiente (setado no YAML). Se não existir, usa ./Encartes
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(Path.cwd() / "Encartes"))).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Mapeamento Estado -> NOME DA LOJA
LOJAS_ESTADOS = {
    "Maranhão": "Assaí Angelim",
    "Alagoas": "Assaí Maceió Farol",
    "Ceará": "Assaí Bezerra M (Fortaleza)",
    "Pará": "Assaí Belém",
    "Paraíba": "Assaí João Pessoa Geisel",
    "Pernambuco": "Assaí Avenida Recife",
    "Piauí": "Assaí Teresina",
    "Sergipe": "Assaí Aracaju",
    "Bahia": "Assaí Vitória da Conquista",  # CHANGE
}

# Região preferida por estado (quando existir select.regiao)
REGIAO_POR_ESTADO = {
    "Bahia": "Interior",  # CHANGE
}

BASE_URL = "https://www.assai.com.br/ofertas"

# =========================
# DRIVER HEADLESS
# =========================

def build_headless_driver() -> webdriver.Chrome:
    """
    Cria o Chrome em modo headless estável para CI/CD (GitHub Actions).
    Selenium Manager resolve o ChromeDriver automaticamente.
    """
    chrome_opts = Options()
    chrome_opts.add_argument("--headless=new")     # headless moderno
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--window-size=1920,1080")
    chrome_opts.add_argument("--disable-extensions")
    chrome_opts.add_argument("--disable-notifications")
    chrome_opts.add_argument("--start-maximized")  # mantém layout amplo
    # (Downloads via browser não são usados; salvamos via requests)

    # Instancia o driver (Selenium 4+ com Selenium Manager)
    return webdriver.Chrome(options=chrome_opts)

# =========================
# HELPERS
# =========================

def encontrar_data(driver: webdriver.Chrome) -> str:
    try:
        enc_data = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@class, "ofertas-tab-validade")]'))
        )
    except Exception:
        return "sem_data"

    for div in enc_data:
        texto = div.text.strip()
        if texto:
            nome_pasta = re.sub(r'[\\/*?:"<>|\s]', '_', texto)
            return nome_pasta
    return "sem_data"

def aguardar_elemento(driver: webdriver.Chrome, seletor, by=By.CSS_SELECTOR, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, seletor)))

def clicar_elemento(driver: webdriver.Chrome, seletor, by=By.CSS_SELECTOR):
    element = WebDriverWait(driver, 45).until(EC.element_to_be_clickable((by, seletor)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.5)
    element.click()

def scroll_down_and_up(driver: webdriver.Chrome):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
    time.sleep(0.5)
    driver.execute_script("window.scrollTo(0, 1);")
    time.sleep(0.5)

def baixar_encartes(driver: webdriver.Chrome, wait: WebDriverWait, jornal_num: int, download_dir: Path):
    page_num = 1
    downloaded_urls = set()
    while True:
        print(f"  Baixando página {page_num} do jornal {jornal_num}...")
        links_download = wait.until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//a[contains(@class, 'download') and contains(@href, '.jpeg')]")
            )
        )
        current_page_urls = []
        for link in links_download:
            url = link.get_attribute("href")
            if url and url not in downloaded_urls:
                current_page_urls.append(url)
                downloaded_urls.add(url)

        # Se não encontrou URLs novas e já passou da primeira página, encerra
        if not current_page_urls and page_num > 1:
            break

        for idx, url in enumerate(current_page_urls, start=1):
            try:
                response = requests.get(url, timeout=60)
                if response.status_code == 200:
                    file_path = download_dir / f"encarte_jornal_{jornal_num}_pagina_{page_num}_{idx}_{int(time.time())}.jpg"
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                    print(f"  Encarte {file_path.name} salvo.")
                else:
                    print(f"Falha no download: {url} (Status: {response.status_code})")
            except Exception as e:
                print(f"Erro no download: {url} — {e}")

        # Tenta ir para a próxima página do carrossel
        try:
            next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.slick-next")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
            time.sleep(0.5)
            next_button.click()
            time.sleep(2)
            page_num += 1
        except Exception:
            break

def select_by_visible_text_contains(driver: webdriver.Chrome, select_el, target_text, timeout=10):
    WebDriverWait(driver, timeout).until(lambda d: len(select_el.find_elements(By.TAG_NAME, "option")) > 0)
    sel = Select(select_el)
    opts = select_el.find_elements(By.TAG_NAME, "option")
    alvo_norm = target_text.strip().lower()
    for o in opts:
        if alvo_norm in o.text.strip().lower():
            sel.select_by_visible_text(o.text)
            return True
    return False

# =========================
# MAIN
# =========================

def main():
    driver = build_headless_driver()
    wait = WebDriverWait(driver, 45)

    try:
        driver.get(BASE_URL)
        time.sleep(2)

        # Fecha eventual popup de cookies
        try:
            clicar_elemento(driver, "button.ot-close-icon")
        except Exception:
            pass

        clicar_elemento(driver, "a.seletor-loja")
        time.sleep(1)

        for estado, loja in LOJAS_ESTADOS.items():
            print(f" Processando: {estado} - {loja}")

            estado_select = aguardar_elemento(driver, "select.estado")
            Select(estado_select).select_by_visible_text(estado)
            time.sleep(1)

            # Se houver seletor de região para o estado, seleciona
            if estado in REGIAO_POR_ESTADO:
                try:
                    regiao_select_element = aguardar_elemento(driver, "select.regiao", timeout=15)
                    Select(regiao_select_element).select_by_visible_text(REGIAO_POR_ESTADO[estado])
                    aguardar_elemento(driver, "select.loja option[value]", timeout=20)
                    time.sleep(0.5)
                except Exception as e:
                    print(f" Não foi possível selecionar a região para {estado}: {e}")

            # Seleciona a loja (exato ou contém)
            loja_select = aguardar_elemento(driver, "select.loja", timeout=20)
            try:
                Select(loja_select).select_by_visible_text(loja)
            except Exception:
                ok = select_by_visible_text_contains(driver, loja_select, loja)
                if not ok:
                    raise RuntimeError(f"Não encontrei a loja '{loja}' no estado {estado}")

            time.sleep(0.8)

            clicar_elemento(driver, "button.confirmar")
            time.sleep(1)

            aguardar_elemento(driver, "div.ofertas-slider", timeout=45)
            data_nome = encontrar_data(driver)

            nome_loja = loja.replace(' ', '_').replace('(', '').replace(')', '')
            download_dir = OUTPUT_DIR / f"ASSAI_encartes_{nome_loja}_{data_nome}"
            download_dir.mkdir(parents=True, exist_ok=True)

            # Jornal 1
            scroll_down_and_up(driver)
            baixar_encartes(driver, wait, 1, download_dir)

            # Tenta Jornal 2 e 3
            for i in range(2, 4):
                try:
                    clicar_elemento(driver, f"//button[contains(., 'Jornal de Ofertas {i}')]", By.XPATH)
                    time.sleep(3)
                    aguardar_elemento(driver, "div.ofertas-slider", timeout=45)
                    scroll_down_and_up(driver)
                    baixar_encartes(driver, wait, i, download_dir)
                except Exception as e:
                    print(f" Jornal {i} indisponível para {loja}: {str(e)}")

            # Volta para o seletor de loja para próximo estado
            clicar_elemento(driver, "a.seletor-loja")
            time.sleep(2)

        print("Todos os encartes foram processados!")

    except Exception as e:
        print(f"Erro crítico: {str(e)}")
        # Salva screenshot de erro dentro do OUTPUT_DIR (para ir como artefato)
        try:
            err_shot = OUTPUT_DIR / "erro_encartes_assai.png"
            driver.save_screenshot(str(err_shot))
            print(f"Screenshot de erro salvo em: {err_shot}")
        except Exception as se:
            print(f"Falha ao salvar screenshot: {se}")

        # também salva um log simples
        try:
            (OUTPUT_DIR / "erro_encartes_assai.log").write_text(f"{datetime.now()}: {e}\n", encoding="utf-8")
        except Exception:
            pass
        # Retorna código de erro para o job acusar falha (opcional; se preferir continuar, comente)
        # sys.exit(1)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
