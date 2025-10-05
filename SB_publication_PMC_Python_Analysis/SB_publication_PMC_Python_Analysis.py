
import time
import json
import re
import pandas as pd
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Set the maximum number of rows to crawl. Set to None to crawl all; for testing, set to 3
MAX_ROWS = None

def setup_driver():
    options = Options()
    #options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(options=options)

def safe_xpath_text(driver, xpath):
    try:
        return driver.find_element(By.XPATH, xpath).text.strip()
    except:
        return ""

def safe_xpath_texts(driver, xpath):
    try:
        return [el.text.strip() for el in driver.find_elements(By.XPATH, xpath) if el.text.strip()]
    except:
        return []

def parse_citation_string(citation):
    result = {
        "published_year": "",
        "published_month": "",
        "published_day": "",
        "volume": "",
        "issue": "",
        "page_or_article_id": ""
    }
    try:
        date_match = re.search(r"(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})", citation)
        if date_match:
            result["published_year"] = date_match.group(1)
            result["published_month"] = date_match.group(2)
            result["published_day"] = date_match.group(3)
        vi_match = re.search(r"(\d+)\((\d+)\):([^\s]+)", citation)
        if vi_match:
            result["volume"] = vi_match.group(1)
            result["issue"] = vi_match.group(2)
            result["page_or_article_id"] = vi_match.group(3).rstrip(".")
    except Exception as e:
        result["error"] = str(e)
    return result

def extract_pubmed_details(pmid, driver):
    citation_count, mesh_terms, abstract, figure_count = "", "", "", 0
    try:
        # Step 1: citation count
        citation_url = f"https://pubmed.ncbi.nlm.nih.gov/?linkname=pubmed_pubmed_citedin&from_uid={pmid}"
        driver.get(citation_url)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "/html/body/main/div[9]/div[2]/div[2]/div[1]"))
        )

        citation_block = safe_xpath_text(driver, "/html/body/main/div[9]/div[2]/div[2]/div[1]")
        #print(f"[DEBUG] Citation block content: {citation_block}")

        citation_match = re.search(r"(\d+)", citation_block)
        if citation_match:
            citation_count = citation_match.group(1)
        else:
            citation_count = "0"

        # Step 2: pubmed main page
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        driver.get(pubmed_url)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'abstract')]"))
        )

        # Abstract
        abstract_paragraphs = safe_xpath_texts(driver, "//div[contains(@class, 'abstract')]//p")
        abstract = "\n".join(abstract_paragraphs)
        #print(f"[DEBUG] Abstract:\n{abstract}")

        # MeSH Terms
        mesh_terms = "; ".join(safe_xpath_texts(driver, "//div[@id='mesh-terms']//ul/li/div/button[@data-pinger-ignore]"))
        #print(f"[DEBUG] MeSH Terms: {mesh_terms}")

        # Figures (optional)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//main/div[4]/div[1]//figure"))
            )
        except:
            pass
        figure_count = len(driver.find_elements(By.XPATH, "//main/div[4]/div[1]//figure"))
        #print(f"[DEBUG] Figure Count: {figure_count}")
        

    except Exception as e:
        print(f"[PMID {pmid}] PubMed fetch error:", e)

    return citation_count, mesh_terms, abstract, figure_count

def extract_article_metadata(driver, url, index, original_title):
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'usa-in-page-nav__list')]"))
        )

        toc_items = driver.find_elements(By.XPATH, "//ul[contains(@class, 'usa-in-page-nav__list')]//a[@data-ga-label]")
        toc = [a.get_attribute("data-ga-label").strip() for a in toc_items if a.get_attribute("data-ga-label").strip()]

        citation_string = safe_xpath_text(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]/section[1]/div")
        citation_info = parse_citation_string(citation_string)
        doi = safe_xpath_text(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]/section[1]/div/a")

        section1_text = safe_xpath_text(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]")
        pmcid = re.search(r"PMCID:\s*(PMC\d+)", section1_text)
        pmid = re.search(r"PMID:\s*(\d+)", section1_text)
        pmcid = pmcid.group(1) if pmcid else ""
        pmid = pmid.group(1) if pmid else ""

        metadata = {
            "id": index,
            "original_title": original_title,
            "url": url,
            "pmcid": pmcid,
            "pmid": pmid,
            "publisher": safe_xpath_text(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]/section[1]/div/div/button"),
            "citation_string": citation_string,
            "citation_parsed": citation_info,
            "doi": doi,
            "doi_link": f"https://doi.org/{doi}" if doi else "",
            "link_title": safe_xpath_text(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]/section[2]/div/hgroup/h1"),
            "authors": safe_xpath_texts(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]/section[2]/div/div[1]//span[@class='name western']"),
            "editors": safe_xpath_texts(driver, "/html/body/div[3]/div[2]/div/div[1]/div/div[2]/main/article/section[1]/section[2]/div/div[2]//span[@class='name western']"),
            "on_this_page": toc
        }

        if pmid:
            citation_count, mesh_terms, abstract, figure_count = extract_pubmed_details(pmid, driver)
            metadata["citation_count"] = citation_count
            metadata["mesh_terms"] = mesh_terms
            metadata["abstract"] = abstract
            metadata["figure_count"] = figure_count

        return metadata
    except Exception as e:
        return {"id": index, "url": url, "error": str(e)}

def main():
    start_time = time.time()
    base_path = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_path, "SB_publication_PMC.csv")
    df = pd.read_csv(csv_path)

    total_rows = len(df)
    df_to_process = df if MAX_ROWS is None else df.head(MAX_ROWS)
    actual_rows = len(df_to_process)

    results = []
    driver = setup_driver()

    for i, row in df_to_process.iterrows():
        index = i + 1
        print(f"[{index}/{total_rows}] {row['Link']}")
        results.append(extract_article_metadata(driver, row["Link"], index, row["Title"]))
        time.sleep(1)

    driver.quit()

    output_path = os.path.join(base_path, "space_biology_metadata.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Export JSON to Excel (flattened)
    flat_rows = []
    for entry in results:
        if "error" in entry:
            flat_rows.append({
                "ID": entry.get("id"),
                "Original Title": entry.get("original_title"),
                "Link": entry.get("url"),
                "Error": entry["error"]
            })
            continue

        citation = entry.get("citation_parsed", {})
        flat_rows.append({
            "ID": entry.get("id"),
            "Original Title": entry.get("original_title"),
            "Link": entry.get("url"),
            "pmcid": entry.get("pmcid"),
            "pmid": entry.get("pmid"),
            "Publisher": entry.get("publisher"),
            "Published Date": f"{citation.get('published_year','')},{citation.get('published_month','')},{citation.get('published_day','')}",
            "Volume": citation.get("volume"),
            "Issue": citation.get("issue"),
            "Page/Article ID": citation.get("page_or_article_id"),
            "DOI": entry.get("doi"),
            "DOI Link": entry.get("doi_link"),
            "Link Title": entry.get("link_title"),
            "Authors": ", ".join(entry.get("authors", [])),
            "Editors": ", ".join(entry.get("editors", [])),
            "Sections (On This Page)": ", ".join(entry.get("on_this_page", [])),
            "Citation Count": entry.get("citation_count", ""),
            "MeSH Terms": entry.get("mesh_terms", ""),
            "Abstract": entry.get("abstract", ""),
            "Figure Count": entry.get("figure_count", "")
        })

    excel_path = os.path.join(base_path, "SB_publications_PMC_metadata_result.xlsx")
    pd.DataFrame(flat_rows).to_excel(excel_path, index=False)
    print(f"📄 Excel file saved to: {excel_path}")

    elapsed_time = time.time() - start_time
    print(f"✅ Done! Saved to: {output_path}")
    print(f"⏱️ Total time: {elapsed_time:.2f} seconds")
    print(f"📄 Total articles crawled: {actual_rows} (out of {total_rows})")

if __name__ == "__main__":
    main()
