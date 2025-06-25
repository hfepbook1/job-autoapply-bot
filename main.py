def apply_to_job(job):
    print(f"[AUTO] Applying → {job['url']}", flush=True)
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(job["url"])
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        # fill inputs
        for inp in driver.find_elements(By.TAG_NAME, "input"):
            name = (inp.get_attribute("name") or "").lower()
            if "email" in name:
                inp.send_keys(USER_DATA.get("email",""))
            elif "name" in name:
                inp.send_keys(USER_DATA.get("full_name",""))
            elif "phone" in name:
                inp.send_keys(USER_DATA.get("phone",""))
        # upload resume
        for f in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            f.send_keys(os.path.abspath(RESUME_PATH))

        # gather candidates: button.apply, a.apply, input[type=submit]
        candidates = []
        candidates += driver.find_elements(By.XPATH,
            "//button[contains(translate(text(),'APPLY','apply'),'apply')]")
        candidates += driver.find_elements(By.XPATH,
            "//a[contains(translate(text(),'APPLY','apply'),'apply')]")
        candidates += driver.find_elements(By.CSS_SELECTOR,
            "input[type='submit']")
        # pick the first visible & enabled
        apply_btn = None
        for el in candidates:
            if el.is_displayed() and el.is_enabled():
                apply_btn = el
                break

        if not apply_btn:
            # debug: list what elements we saw
            snippets = [el.get_attribute("outerHTML") for el in candidates]
            print("[AUTO ERROR] No APPLY element found; candidates were:", flush=True)
            for s in snippets:
                print(s, flush=True)
            return

        # click via JS
        driver.execute_script("arguments[0].scrollIntoView(true);", apply_btn)
        driver.execute_script("arguments[0].click();", apply_btn)
        print("[AUTO] Success", flush=True)

    except Exception as e:
        print(f"[AUTO ERROR] {e}", flush=True)
    finally:
        driver.quit()
