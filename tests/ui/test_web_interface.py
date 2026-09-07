"""Browser regressions for the served static UI, with no live backend access.

Run: .venv/bin/python -m pytest tests/ui -q
Install browser: .venv/bin/playwright install chromium
UI_BROWSER=webkit selects WebKit after installing that browser.
Artifacts: .cache/ui-audit/ (screenshots and route inventory).
"""
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

playwright = pytest.importorskip('playwright.sync_api')
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / '.cache/ui-audit'


@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as p:
        b = getattr(p, os.environ.get('UI_BROWSER', 'chromium')).launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
    page = context.new_page()
    errors, requests = [], []
    page.add_init_script("""(() => {const d=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');window._clears=[];Object.defineProperty(HTMLTextAreaElement.prototype,'value',{...d,set(v){if(this.id==='message' && this.value && !v)window._clears.push(new Error().stack);d.set.call(this,v)}})})();""")
    page.on('pageerror', lambda e: errors.append(str(e)))
    def route(r):
        url = urlparse(r.request.url)
        path = unquote(url.path)
        requests.append((r.request.method, path))
        if path.startswith('/static/'):
            file = (ROOT / path.lstrip('/')).resolve()
            if file.is_relative_to(ROOT / 'static') and file.is_file():
                return r.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
            return r.fulfill(status=404, body='Missing fixture asset')
        if not path.startswith('/api/'):
            file = ROOT / ('static/login.html' if path == '/login' else 'static/index.html')
            return r.fulfill(body=file.read_text(), content_type='text/html')
        data = {}
        if path == '/api/auth/status':
            data = {'authenticated': True, 'username': 'UI Test', 'is_admin': True}
        elif path == '/api/auth/settings':
            data = {'stt_provider': 'disabled'}
        elif path in ('/api/sessions', '/api/notes', '/api/presets/templates', '/api/calendar/events',
                      '/api/calendar/calendars', '/api/fonts/custom', '/api/research/library',
                      '/api/gallery/albums', '/api/contacts'):
            data = []
        elif path == '/api/models':
            data = {'items': []}
        elif path == '/api/memory':
            data = {'memories': [], 'facts': [], 'episodes': []}
        elif path == '/api/gallery/library':
            data = {'items': [], 'total': 0}
        return r.fulfill(json=data)
    context.route('**/*', route)
    page.goto('http://monikai.test/', wait_until='networkidle')
    page.wait_for_function("typeof window._updateSendBtnIcon === 'function'")
    page.wait_for_timeout(200)
    page.ui_errors = errors
    page.ui_requests = requests
    yield page
    context.close()


def assert_in_view(page, selector):
    box = page.locator(selector).bounding_box()
    assert box, (selector, page.locator(selector).evaluate("e=>({html:e.outerHTML,value:document.querySelector('#message').value,clears:window._clears})"))
    assert box['x'] >= -1, (selector, box)
    assert box['x'] + box['width'] <= page.viewport_size['width'] + 1, (selector, box)
    assert box['y'] >= -1, (selector, box)
    assert box['y'] + box['height'] <= page.viewport_size['height'] + 1, (selector, box)


@pytest.mark.parametrize('width,height', [(360,800),(390,844),(768,900),(1024,768),(1440,900),(844,390)])
def test_composer_layout_and_states(page, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    page.reload(wait_until='networkidle')
    page.wait_for_function("typeof window._updateSendBtnIcon === 'function'")
    field = page.locator('#message')
    assert page.locator('#user-bar-name').count() == 1
    assert page.locator('#group-toggle').count() == 1
    assert field.count() == 1
    field.fill('First line\nSecond line ' + 'very-long-word' * 20)
    playwright.expect(page.locator('#send-btn')).to_be_visible()
    for selector in ('#message','.composer-pill','#send-btn','#composer-mic-btn','#overflow-plus-btn'):
        assert_in_view(page, selector)
    field.press('Shift+Enter')
    assert field.input_value().endswith('\n')
    assert not any(path == '/api/chat_stream' for _, path in page.ui_requests)
    field.fill('   ')
    playwright.expect(page.locator('#send-btn')).to_be_visible()
    # A stop action must remain reachable without a draft.
    page.evaluate("""() => { const b=document.querySelector('#send-btn'); b.dataset.mode='streaming'; window._updateSendBtnIcon(); }""")
    playwright.expect(page.locator('#send-btn')).to_be_visible()
    playwright.expect(page.locator('#send-btn')).to_have_attribute('aria-label','Stop generation')
    field.fill('Queued message')
    playwright.expect(page.locator('#send-btn')).to_have_attribute('aria-label','Queue message')
    assert not page.ui_errors
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / f'composer-{width}x{height}.png'))


def test_theme_font_and_reload(page):
    page.evaluate("""async () => {
      const theme = await import('/static/js/theme.js');
      const colors={bg:'#faf8f5', fg:'#242424', panel:'#ffffff', border:'#cccccc', red:'#9b3555',
        advanced:{inputBg:'#f1e6f3', sidebarBg:'#ebe0ee', userBubbleBg:'#eeddee'}};
      theme.applyColors(colors); theme.applyFontDensity('serif','comfortable');
      localStorage.setItem('odysseus-theme',JSON.stringify({colors,font:'serif',density:'comfortable'}));
    }""")
    for reload in (False, True):
        if reload:
            page.reload(wait_until='networkidle')
        assert page.locator('body').evaluate("e=>getComputedStyle(e).backgroundColor") == 'rgb(250, 248, 245)'
        assert page.locator('.composer-pill').evaluate("e=>getComputedStyle(e).backgroundColor") == 'rgb(241, 230, 243)'
        assert page.locator('#sidebar').evaluate("e=>getComputedStyle(e).backgroundColor") == 'rgb(235, 224, 238)'
        assert 'Georgia' in page.locator('#message').evaluate("e=>getComputedStyle(e).fontFamily")
    assert not page.ui_errors


def test_mobile_tools_and_sidebar_keyboard(page):
    page.set_viewport_size({'width':390,'height':844})
    page.reload(wait_until='networkidle')
    page.wait_for_function("typeof window._updateSendBtnIcon === 'function'")
    page.locator('#hamburger-btn').click()
    playwright.expect(page.locator('#sidebar')).to_be_visible()
    assert_in_view(page, '#sidebar')
    page.locator('#sidebar-toggle-btn').click()
    playwright.expect(page.locator('#hamburger-btn')).to_have_attribute('aria-expanded','false')
    plus = page.locator('#overflow-plus-btn')
    plus.focus()
    plus.press('Enter')
    playwright.expect(plus).to_have_attribute('aria-expanded','true')
    assert_in_view(page, '#overflow-menu')
    assert page.evaluate("document.querySelector('#overflow-menu').contains(document.activeElement)")
    page.keyboard.press('Escape')
    playwright.expect(page.locator('#overflow-menu')).to_be_hidden()
    playwright.expect(plus).to_be_focused()
    assert not page.ui_errors


def test_attachment_only_send_and_hidden_tools(page):
    page.locator('#file-input').set_input_files({'name':'example.txt','mimeType':'text/plain','buffer':b'Fixture attachment'})
    playwright.expect(page.locator('#send-btn')).to_be_visible()
    page.evaluate("""() => {const chip=document.querySelector('#web-chip');chip.style.display='';chip.style.outline='none';}""")
    playwright.expect(page.locator('#web-chip')).to_be_visible()
    page.evaluate("document.querySelector('#web-chip').hidden=true")
    playwright.expect(page.locator('#web-chip')).to_be_hidden()
    assert not page.ui_errors


@pytest.mark.parametrize('route', ['/notes','/calendar','/email','/tasks','/library','/memory','/gallery',
    '/cookbook','/compare','/research','/theme','/settings','/vault','/contacts','/backgrounds'])
def test_workspace_routes(page, route):
    page.goto('http://monikai.test'+route, wait_until='networkidle')
    page.wait_for_timeout(400)
    assert page.locator('body').inner_text().strip()
    assert not page.ui_errors
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / (route[1:]+'.png')))
    (ARTIFACTS / (route[1:]+'-requests.json')).write_text(json.dumps(page.ui_requests, indent=2))
