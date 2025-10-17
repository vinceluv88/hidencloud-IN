import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 全局配置 ---
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
SERVICE_URL = "https://dash.hidencloud.com/service/72119/manage"
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def login(page):
    log("开始登录流程...")
    if not HIDENCLOUD_COOKIE:
        log("❌ 未提供 Cookie，无法登录")
        return False

    page.context.add_cookies([{
        'name': COOKIE_NAME,
        'value': HIDENCLOUD_COOKIE,
        'domain': 'dash.hidencloud.com',
        'path': '/',
        'httpOnly': True,
        'secure': True,
        'sameSite': 'Lax'
    }])
    log("Cookie 已设置，访问服务管理页面...")
    page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
    if "auth/login" in page.url:
        log("❌ Cookie 登录失败")
        return False
    log("✅ Cookie 登录成功！")
    return True

def renew_service(page):
    try:
        log("开始续费任务...")
        if page.url != SERVICE_URL:
            log(f"导航至服务页面: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)

        # 步骤 1: 点击 'Renew'
        log("步骤 1: 点击 'Renew'")
        renew_btn = page.locator('button:has-text("Renew"), a:has-text("Renew")')
        renew_btn.first.wait_for(state="visible", timeout=60000)
        renew_btn.first.click()
        log("✅ 'Renew' 已点击")
        time.sleep(1)

        # 步骤 2: 点击 'Create Invoice' 并等待网络响应
        log("步骤 2: 点击 'Create Invoice' 并等待新发票 URL")
        create_invoice_btn = page.locator('button:has-text("Create Invoice"), a:has-text("Create Invoice")')
        create_invoice_btn.first.wait_for(state="visible", timeout=60000)
        create_invoice_btn.first.click()
        log("✅ 'Create Invoice' 已点击，等待网络响应...")

        try:
            response = page.wait_for_response(
                lambda resp: "/payment/invoice/" in resp.url,
                timeout=60000
            )
            new_invoice_url = response.url
            log(f"🎉 捕获到新发票 URL: {new_invoice_url}")
        except PlaywrightTimeoutError:
            raise Exception("❌ 未能捕获新发票 URL")

        # 步骤 3: 跳转到新发票页面
        log(f"步骤 3: 跳转到新发票页面 {new_invoice_url}")
        page.goto(new_invoice_url, wait_until="networkidle", timeout=60000)

        # 步骤 4: 查找可见的 'Pay' 按钮
        log("步骤 4: 查找可见的 'Pay' 按钮")
        pay_btn = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_btn.wait_for(state="visible", timeout=60000)
        pay_btn.click()
        log("✅ 'Pay' 按钮已点击，续费完成")
        page.screenshot(path="renew_success.png")
        return True

    except PlaywrightTimeoutError as e:
        log(f"❌ 超时错误: {e}")
        page.screenshot(path="renew_timeout.png")
        return False
    except Exception as e:
        log(f"❌ 续费失败: {e}")
        page.screenshot(path="renew_error.png")
        return False

def main():
    if not HIDENCLOUD_COOKIE:
        log("❌ 必须提供 HIDENCLOUD_COOKIE")
        sys.exit(1)

    with sync_playwright() as p:
        browser = None
        try:
            log("启动浏览器...")
            browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            if not login(page):
                log("登录失败，退出")
                sys.exit(1)

            if not renew_service(page):
                log("续费失败，退出")
                sys.exit(1)

            log("🎉 自动续费完成！")

        except Exception as e:
            log(f"💥 主程序异常: {e}")
            if 'page' in locals() and page:
                page.screenshot(path="main_error.png")
            sys.exit(1)
        finally:
            log("关闭浏览器")
            if browser:
                browser.close()

if __name__ == "__main__":
    main()
