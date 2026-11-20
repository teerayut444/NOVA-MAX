import subprocess
import sys
import argparse
import time
from pathlib import Path
import requests

_ROOT_DIR = Path(__file__).parent.parent.resolve()
_PY_SCRAPER_DIR = _ROOT_DIR / "Py Scraper"
if str(_PY_SCRAPER_DIR) not in sys.path and _PY_SCRAPER_DIR.exists():
    sys.path.insert(0, str(_PY_SCRAPER_DIR))

try:
    from logger_util import safe_ssl_get
except ImportError:
    safe_ssl_get = None

# Reconfigure stdout to UTF-8 to prevent encoding crashes on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TARGET_URLS = {
    "LED": "https://asset.led.go.th/newbidreg/",
    "SAM": "https://sam.or.th/site/npa/page_list.php",
    "BAM": "https://www.bam.co.th/th/npa/property/search",
    "Chayo555": "https://asset.chayo555.com",
    "GHB": "https://www.ghbhomecenter.com",
    "KBANK": "https://www.kasikornbank.com/th/property-for-sale",
    "KTB": "https://krungthai.com/th/krungthai-property",
    "SCB": "https://asset.scb.co.th",
    "GSB": "https://npa-assets.gsb.or.th/",
    "DDproperty": "https://www.ddproperty.com",
    "Livinginsider": "https://www.livinginsider.com",
    "NaYoo": "https://nayoo.co/",
    "ZmyHome": "https://zmyhome.com/buy",
    "Baania": "https://www.baania.com/s/%E0%B8%97%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%AB%E0%B8%A1%E0%B8%94/listing"
}

SCRAPERS = [
    {"name": "LED", "script": "scrape_led_monthly.py"},
    {"name": "SAM", "script": "scrape_sam_monthly.py"},
    {"name": "BAM", "script": "scrape_bam_monthly.py"},
    {"name": "Chayo555", "script": "scrape_chayo555_monthly.py"},
    {"name": "GHB", "script": "scrape_ghb_monthly.py"},
    {"name": "KBANK", "script": "scrape_kbank_monthly.py"},
    {"name": "KTB", "script": "scrape_ktb_monthly.py"},
    {"name": "SCB", "script": "scrape_scb_monthly.py"},
    {"name": "GSB", "script": "scrape_gsb_monthly.py"},
    {"name": "DDproperty", "script": "scrape_ddproperty_monthly.py"},
    {"name": "Livinginsider", "script": "scrape_livinginsider_monthly.py"},
    {"name": "NaYoo", "script": "scrape_nayoo_monthly.py"},
    {"name": "ZmyHome", "script": "scrape_zmyhome_monthly.py"},
    {"name": "Baania", "script": "scrape_baania_monthly.py"}
]

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

def check_website_accessibility(name: str, url: str) -> bool:
    """ตรวจสอบว่าเว็บปลายทางสามารถเชื่อมต่อและตอบสนองได้ตามปกติหรือไม่"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    t0 = time.time()
    try:
        if safe_ssl_get is not None:
            session_obj = curl_requests.Session(impersonate="chrome120") if HAS_CURL_CFFI else None
            r = safe_ssl_get(url, session=session_obj, headers=headers, timeout=12, ssl_fallback_on_gov=True)
        else:
            r = requests.get(url, headers=headers, timeout=12, verify=True)
        elapsed = time.time() - t0
        if r.status_code in [200, 202, 301, 302, 307, 308, 403, 429]:
            status_label = "ONLINE" if r.status_code < 400 else f"ONLINE (WAF {r.status_code})"
            print(f"[Health Check] 🟢 {name} ({url}) | สถานะ: {status_label} (HTTP {r.status_code}) | ตอบสนองใน {elapsed:.2f} วินาที")
            return True
        else:
            print(f"[Health Check] ⚠️ {name} ({url}) | สถานะ: HTTP Error {r.status_code} | เวลา: {elapsed:.2f} วินาที")
            return False
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[Health Check] ❌ {name} ({url}) | ไม่สามารถเข้าถึงได้ ({e}) | เวลา: {elapsed:.2f} วินาที")
        return False

def run_scraper(name: str, script_name: str, cwd: Path, args_list: list, target_url: str = None) -> bool:
    print(f"\n==========================================")
    print(f"กำลังเริ่มรันระบบดึงข้อมูล: {name}")
    print(f"Directory: {cwd}")
    print(f"Command: python {script_name} {' '.join(args_list)}")
    print(f"==========================================")
    
    # 1. Pre-flight health check
    url = target_url or TARGET_URLS.get(name)
    if url:
        is_online = check_website_accessibility(name, url)
        if not is_online:
            print(f"\n[Skip Warning] ⚠️ ข้ามการรันระบบดึงข้อมูลของ {name} เนื่องจากเซิร์ฟเวอร์เว็บปลายทางไม่ตอบสนองหรือขัดข้องชั่วคราว\n")
            return False
    
    python_exe = sys.executable
    cmd = [python_exe, script_name] + args_list
    
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                sys.stdout.write(output)
                sys.stdout.flush()
                
        rc = process.poll()
        if rc == 0:
            print(f"\n[Success] ดึงข้อมูลของ {name} สำเร็จเรียบร้อย!")
            return True
        else:
            print(f"\n[Warning] ระบบขูดของ {name} จบการทำงานด้วยรหัสข้อผิดพลาด: {rc}")
            return False
            
    except KeyboardInterrupt:
        print(f"\n[Interrupt] ผู้ใช้สั่งหยุดการทำงานของ {name}...")
        raise
    except Exception as e:
        print(f"\n[Error] ไม่สามารถรัน Scraper ของ {name} ได้: {e}")
        return False
    finally:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                pass

def main():
    parser = argparse.ArgumentParser(description="Run all asset scrapers from Py Scraper.")
    parser.add_argument("--sequential", action="store_true", help="รันทีละบริษัทตามลำดับ (Sequential Mode)")
    parser.add_argument("--parallel", action="store_true", default=True, help="รันแบบขนานพร้อมกันทุกบริษัท (Fast Mode - ค่าเริ่มต้น)")
    args, extra_args = parser.parse_known_args()
    
    root_dir = Path(__file__).parent.parent.resolve()
    monthly_dir = root_dir / "Py Scraper" if (root_dir / "Py Scraper").exists() else root_dir / "Monthly all new"
    
    if not args.sequential:
        print("🚀 รันระบบดึงข้อมูลแบบคู่ขนานทุกแพลตฟอร์มพร้อมกันผ่าน run_parallel_monthly.py...")
        p_script = monthly_dir / "run_parallel_monthly.py"
        res = subprocess.run([sys.executable, str(p_script), "--parallel"] + extra_args, cwd=monthly_dir)
        sys.exit(res.returncode)

    print("\n==========================================================================")
    print(" 🔍 ตรวจสอบความพร้อมการเชื่อมต่อเว็บไซต์ปลายทาง (Website Health Check)")
    print(" 📂 อ้างอิงโฟลเดอร์หลัก: Py Scraper")
    print("==========================================================================")
    
    any_failed = False
    for s in SCRAPERS:
        run_args = list(extra_args)
        if s["name"] == "LED" and "--skip-coords" not in run_args:
            run_args.append("--skip-coords")
        ok = run_scraper(
            name=s["name"],
            script_name=s["script"],
            cwd=monthly_dir,
            args_list=run_args
        )
        if not ok:
            any_failed = True
        if s["name"] == "LED" and ok:
            # Explicit Q2 sequential chain: LED -> LED_Legal -> LandsMaps -> LandsMaps-Merge
            run_scraper("LED_Legal", "scrape_led_legal.py", cwd=monthly_dir, args_list=list(extra_args))
            run_scraper(
                "LandsMaps",
                "enrich_led_landsmaps.py",
                cwd=monthly_dir,
                args_list=["--limit", "0", "--workers", "1", "--no-merge"]
                + (["--now"] if "--now" in extra_args else []),
                target_url="https://landsmaps.dol.go.th/",
            )
            run_scraper(
                "LandsMaps-Merge",
                "enrich_led_merge_landsmaps.py",
                cwd=monthly_dir,
                args_list=["--no-merge"] + (["--now"] if "--now" in extra_args else []),
                target_url="https://landsmaps.dol.go.th/",
            )
    
    # รวมข้อมูลเป็น all_assets_monthly_YYYY_MM.csv และแปลงเฉพาะไฟล์นี้เป็น all_assets.parquet
    print("\n==========================================")
    print("กำลังเริ่มรวมข้อมูล CSV และแปลงเป็น all_assets.parquet...")
    print("==========================================\n")
    
    try:
        sys.path.insert(0, str(monthly_dir))
        import merge_csv_monthly
        merge_csv_monthly.merge_monthly_csv()
    except Exception as e:
        print(f"\n[Error] เกิดข้อผิดพลาดในการรวมและแปลงข้อมูล: {e}")

    print("\n" + "=" * 80, flush=True)
    print("🏁 ทุกขั้นตอนเสร็จสมบูรณ์ 100% แล้ว สามารถตรวจสอบผลลัพธ์และปิดหน้าต่างนี้ได้", flush=True)
    print("=" * 80, flush=True)
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n👉 กดปุ่ม Enter เพื่อปิดหน้าต่างนี้...")
    except Exception:
        pass
    sys.exit(1 if any_failed else 0)

if __name__ == "__main__":
    main()
