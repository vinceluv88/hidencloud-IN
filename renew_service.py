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
    """
    登录流程：
    1. 优先尝试使用 Cookie 登录。
    2. 若失败则回退至账号密码登录。
    """
    log("开始登录流程...")

    # --- 优先尝试 Cookie 登录 ---
    if HIDENCLOUD_COOKIE:
        log("检测到 HIDENCLOUD_COOKIE，尝试使用 Cookie 登录。")
        try:
            page.context.add_cookies([{
                'name': COOKIE_NAME,
                'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com',
                'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
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

    # --- 使用账号密码登录 ---
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        log("❌ 无法登录：未提供 Cookie 或账号密码。")
        return False

    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        log("登录页面已加载。")

        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        log("邮箱和密码已填写。")

        # --- 处理 Cloudflare Turnstile ---
        log("正在处理 Cloudflare Turnstile 验证...")
        turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        checkbox = turnstile_frame.locator('input[type="checkbox"]')

        checkbox.wait_for(state="visible", timeout=30000)
        checkbox.click()
        log("✅ Turnstile 验证点击成功，等待验证完成...")

        page.wait_for_function(
            "() => document.querySelector('[name=\"cf-turnstile-response\"]') && document.querySelector('[name=\"cf-turnstile-response\"]').value",
            timeout=60000
        )
        log("✅ Turnstile 验证完成！")

        page.click('button[type="submit"]:has-text("Sign in to your account")')
        log("已点击登录按钮，等待跳转...")

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

        # Step 0: 确保在目标页面
        if page.url != SERVICE_URL:
            log(f"导航到: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
        log("服务管理页面已加载。")

        # Step 1: 点击 Renew
        log("步骤 1: 点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")')
        renew_button.wait_for(state="visible", timeout=30000)
        renew_button.click()
        log("✅ 'Renew' 已点击。")

        log("等待 0.9 秒...")
        time.sleep(0.9)

        # Step 2: 监听 Create Invoice 响应
        log("步骤 2: 捕获发票生成请求...")
        new_invoice_url = None

        def handle_response(response):
            nonlocal new_invoice_url
            if "/payment/invoice/" in response.url:
                new_invoice_url = response.url
                log(f"🎉 捕获到发票 URL: {new_invoice_url}")

        page.on("response", handle_response)

        create_invoice_button = page.locator('button:has-text("Create Invoice")')
        create_invoice_button.wait_for(state="visible", timeout=30000)
        create_invoice_button.click()
        log("✅ 'Create Invoice' 已点击，等待发票生成...")

        for _ in range(15):  # 最多等待 15 秒
            if new_invoice_url:
                break
            page.wait_for_timeout(1000)

        page.remove_listener("response", handle_response)

        if not new_invoice_url:
            log("❌ 未捕获到发票 URL。")
            page.screenshot(path="invoice_error.png")
            raise Exception("未能获取发票 URL。")

        # Step 3: 跳转到发票页面
        log(f"跳转到发票页面: {new_invoice_url}")
        page.goto(new_invoice_url, wait_until="networkidle", timeout=60000)

        # Step 4: 查找并点击 Pay
        log("步骤 3: 查找 'Pay' 按钮...")
        page.wait_for_selector('a:has-text("Pay"), button:has-text("Pay")', timeout=30000)
        pay_button = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first

        log("✅ 找到 'Pay' 按钮，点击中...")
        pay_button.click()

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            log("⚠️ Pay 后页面加载可能未完全结束，继续执行。")

        log("✅ 'Pay' 已点击，续费流程触发完成。")
        page.screenshot(path="pay_clicked.png")

        time.sleep(5)
        log("续费流程已结束，请登录后台确认。")
        return True

    except PlaywrightTimeoutError as e:
        log(f"❌ 续费超时: {e}")
        page.screenshot(path="renew_timeout.png")
        return False
    except Exception as e:
        log(f"❌ 续费错误: {e}")
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
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
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

            log("🎉🎉🎉 自动续费流程已成功完成！ 🎉🎉🎉")

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
