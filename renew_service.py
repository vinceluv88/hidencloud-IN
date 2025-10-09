import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 全局配置 ---
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
HIDENCLOUD_EMAIL = os.environ.get('HIDENCLOUD_EMAIL')
HIDENCLOUD_PASSWORD = os.environ.get('HIDENCLOUD_PASSWORD')

# 目标网页 URL
BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
SERVICE_URL = f"{BASE_URL}/service/72119/manage"

# Cookie 名称
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(message):
    """打印带时间戳的日志"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def login(page):
    """登录流程: 优先 Cookie, 失败回退账号密码"""
    log("开始登录流程...")

    if HIDENCLOUD_COOKIE:
        log("检测到 HIDENCLOUD_COOKIE，尝试使用 Cookie 登录。")
        try:
            page.context.add_cookies([{
                'name': COOKIE_NAME,
                'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com',
                'path': '/',
                'expires': int(time.time()) + 3600*24*365,
                'httpOnly': True,
                'secure': True,
                'sameSite': 'Lax'
            }])
            log("Cookie 已设置，访问服务管理页面...")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
            if "auth/login" in page.url:
                log("Cookie 登录失败，回退至账号密码登录。")
                page.context.clear_cookies()
            else:
                log("✅ Cookie 登录成功！")
                return True
        except Exception as e:
            log(f"Cookie 登录错误: {e}")
            page.context.clear_cookies()

    # 使用账号密码登录
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        log("❌ 无法登录：未提供 Cookie 或账号密码。")
        return False

    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        log("登录页面已加载。")
        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        log("邮箱和密码已填写。")

        # Turnstile 人机验证
        log("正在处理 Cloudflare Turnstile...")
        try:
            turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            checkbox = turnstile_frame.locator('input[type="checkbox"]')
            checkbox.wait_for(state="visible", timeout=30000)
            checkbox.click()
            log("已点击 Turnstile 复选框，等待验证完成...")
            page.wait_for_function(
                "() => document.querySelector('[name=\"cf-turnstile-response\"]') && document.querySelector('[name=\"cf-turnstile-response\"]').value",
                timeout=60000
            )
            log("✅ Turnstile 验证完成！")
        except PlaywrightTimeoutError:
            log("⚠️ Turnstile 验证超时，可能无需手动操作。")

        page.click('button[type="submit"]:has-text("Sign in to your account")')
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=60000)
        if "auth/login" in page.url:
            log("❌ 登录失败，请检查凭据。")
            page.screenshot(path="login_failure.png")
            return False
        log("✅ 登录成功！")
        return True

    except PlaywrightTimeoutError as e:
        log(f"❌ 登录超时: {e}")
        page.screenshot(path="login_timeout.png")
        return False
    except Exception as e:
        log(f"❌ 登录错误: {e}")
        page.screenshot(path="login_error.png")
        return False

def renew_service(page):
    """执行续费流程"""
    try:
        log("开始执行续费任务...")
        if page.url != SERVICE_URL:
            log(f"导航到服务管理页面: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
        log("服务管理页面已加载。")

        # Step 1: 点击 Renew
        log("步骤 1: 点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew"), a:has-text("Renew")')
        renew_button.first.wait_for(state="visible", timeout=30000)
        renew_button.first.click()
        log("✅ 'Renew' 已点击。")
        time.sleep(1)

        # Step 2: 点击 Create Invoice
        log("步骤 2: 点击 'Create Invoice' 生成新发票...")
        create_invoice_btn = page.locator('button:has-text("Create Invoice"), a:has-text("Create Invoice")')
        create_invoice_btn.first.wait_for(state="visible", timeout=30000)
        create_invoice_btn.first.click()
        log("✅ 'Create Invoice' 已点击，等待列表刷新...")

        # 等待发票列表刷新
        time.sleep(4)
        page.reload(wait_until="networkidle")

        # Step 3: 获取最新发票链接
        log("步骤 3: 获取最新发票链接...")
        invoice_links = page.eval_on_selector_all(
            'a[href*="/payment/invoice/"]',
            'els => els.map(e => e.href)'
        )
        if not invoice_links:
            raise Exception("未找到发票链接。")
        latest_invoice = invoice_links[0]
        log(f"🎉 最新发票 URL: {latest_invoice}")

        # Step 4: 跳转到发票页面
        log(f"跳转到发票页面: {latest_invoice}")
        page.goto(latest_invoice, wait_until="networkidle")

        # Step 5: 点击 Pay
        log("步骤 4: 查找 'Pay' 按钮...")
        pay_button = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_button.wait_for(state="visible", timeout=60000)
        pay_button.click()
        log("✅ 已点击 Pay 按钮，续费流程触发完成。")
        time.sleep(3)
        page.screenshot(path="renew_success.png")
        return True

    except PlaywrightTimeoutError as e:
        log(f"❌ 续费超时: {e}")
        page.screenshot(path="renew_timeout.png")
        return False
    except Exception as e:
        log(f"❌ 续费失败: {e}")
        page.screenshot(path="renew_error.png")
        return False

def main():
    """主流程"""
    if not HIDENCLOUD_COOKIE and not (HIDENCLOUD_EMAIL and HIDENCLOUD_PASSWORD):
        log("❌ 缺少登录凭据，退出。")
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
                log("登录失败，程序终止。")
                sys.exit(1)

            if not renew_service(page):
                log("续费失败，程序终止。")
                sys.exit(1)

            log("🎉 自动续费任务完成！")

        except Exception as e:
            log(f"💥 主程序异常: {e}")
            if 'page' in locals() and page:
                page.screenshot(path="main_error.png")
            sys.exit(1)
        finally:
            log("关闭浏览器。")
            if browser:
                browser.close()

if __name__ == "__main__":
    main()
