import os
from pathlib import Path
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("MONEY_GRAPH_TEST_URL"), reason="Set MONEY_GRAPH_TEST_URL for the live browser test")


def test_analyst_browser_journey():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(os.environ["MONEY_GRAPH_TEST_URL"])
        frame = page.frame_locator('iframe[title="app.analyst_workspace"]')
        frame.locator('[data-action="auth-mode"][data-mode="register"]').click()
        email = f"qa-{uuid.uuid4().hex[:10]}@example.com"
        frame.locator('#email').fill(email)
        frame.locator('#password').fill("Browser test password!")
        frame.locator('button[type="submit"]').click()
        frame.locator('.recovery-code').wait_for(timeout=60000)
        recovery = frame.locator('.recovery-code').inner_text()
        frame.locator('[data-action="close-modal"]').click()
        frame.locator('#network-svg').wait_for(timeout=60000)
        page.screenshot(path="output/ui-overview.png", animations="disabled")
        first = frame.locator('.node').first
        gid = first.get_attribute('data-gid')
        first.locator('.core').hover()
        assert frame.locator('#graph-tooltip').is_visible()
        assert frame.locator('.edge[stroke="#f5b544"]').count() > 0
        first.locator('.core').click()
        frame.locator('[data-action="dossier"]:not([disabled])').wait_for(timeout=20000)
        assert gid in frame.locator('#node-card').inner_text()
        frame.locator('[data-action="dossier"]').click()
        assert frame.locator('#dossier-modal').is_visible()
        frame.locator('[data-action="close-modal"]').click()
        frame.locator('[data-action="neighbors"]').click()
        frame.locator('#network-svg').wait_for()
        page.screenshot(path="output/ui-network.png", animations="disabled")
        initial_view = frame.locator('#network-svg').get_attribute('viewBox')
        frame.locator('[data-zoom="0.8"]').click()
        assert frame.locator('#network-svg').get_attribute('viewBox') != initial_view
        frame.locator('[data-page="clusters"]').click()
        assert frame.locator('.cluster-card').count() == 67
        page.screenshot(path="output/ui-clusters.png", animations="disabled")
        frame.locator('.cluster-card').first.click()
        assert frame.locator('#graph-mode').input_value() == "cluster"
        frame.locator('[data-page="ranking"]').click()
        frame.locator('#role-filter').select_option("consolidator")
        page.wait_for_timeout(1200)
        assert frame.locator('tbody .badge').all_inner_texts()
        assert set(frame.locator('tbody .badge').all_inner_texts()) == {"CONSOLIDATOR"}
        frame.locator('#search').fill("does-not-exist")
        frame.get_by_text('По заданным фильтрам узлы не найдены.').wait_for(timeout=15000)
        frame.locator('#search').fill("")
        frame.locator('#role-filter').select_option("")
        frame.locator('tbody tr').first.wait_for()
        page.screenshot(path="output/ui-ranking.png", animations="disabled")
        frame.locator('[data-page="stress"]').click()
        frame.locator('.fragment-chart').wait_for(timeout=20000)
        frame.locator('#remove-count').fill("10")
        frame.locator('#remove-count').dispatch_event('change')
        frame.get_by_text('Клиентов после удаления 10 узлов').wait_for(timeout=20000)
        page.screenshot(path="output/ui-stress.png", animations="disabled")
        frame.locator('[data-page="coverage"]').click()
        assert frame.get_by_text('Неизвестно', exact=True).count() == 2
        page.screenshot(path="output/ui-coverage.png", animations="disabled")
        frame.locator('[data-page="exports"]').click()
        with page.expect_download(timeout=20000) as downloaded:
            frame.locator('[data-file="nodes_roles.csv"]').click()
        file = downloaded.value
        assert file.suggested_filename == 'nodes_roles.csv'
        assert Path(file.path()).read_bytes() == Path('output/nodes_roles.csv').read_bytes()
        frame.locator('[data-action="logout"]').click()
        frame.locator('#auth-form').wait_for()
        assert not frame.locator('#network-svg').count()
        frame.locator('#email').fill(email)
        frame.locator('#password').fill("wrong-password")
        frame.locator('button[type="submit"]').click()
        frame.locator('#auth-error:not(.hidden)').wait_for()
        frame.locator('#password').fill("Browser test password!")
        frame.locator('button[type="submit"]').click()
        frame.locator('.rail').wait_for(timeout=20000)
        frame.locator('[data-action="logout"]').click()
        frame.locator('[data-mode="recover"]').click()
        frame.locator('#email').fill(email)
        frame.locator('#password').fill("Recovered test password!")
        frame.locator('#recovery').fill(recovery)
        frame.locator('button[type="submit"]').click()
        frame.locator('.recovery-code').wait_for(timeout=20000)
        assert frame.locator('.recovery-code').inner_text() != recovery
        frame.locator('[data-action="close-modal"]').click()
        page.set_viewport_size({"width": 430, "height": 900})
        frame.locator('[data-page="overview"]').first.click()
        page.screenshot(path="output/ui-mobile.png", animations="disabled")
        assert frame.locator('body').evaluate('(el) => el.scrollWidth <= window.innerWidth + 2')
        page.set_viewport_size({"width": 1600, "height": 1000})
        frame.locator('[data-page="overview"]').first.click()
        frame.locator('[data-action="run"]').click()
        frame.get_by_text('Анализ завершён. Все показатели обновлены.').wait_for(timeout=60000)
        assert frame.locator('[data-action="run"]').is_enabled()
        frame.locator('[data-page="network"]').click()
        frame.locator('[data-tab="flow"]').click()
        assert frame.locator('.flow-chart path').count() > 0, str(errors)
        frame.locator('[data-tab="graph"]').click()
        frame.locator('#graph-mode').select_option('all')
        assert frame.locator('.node').count() == 2248
        import pandas as pd
        data = pd.read_csv('output/node_features.csv')
        for gid in (str(int(data[data.total_degree.eq(0)].gid.iloc[0])), str(int(data[data.is_boundary_node].gid.iloc[0]))):
            frame.locator('#search').fill(gid)
            frame.locator('.search-result[data-gid="'+gid+'"]').click()
            frame.locator('[data-action="dossier"]:not([disabled])').wait_for(timeout=20000)
            assert gid in frame.locator('#node-card').inner_text()
        frame.locator('[data-page="overview"]').first.click()
        page.screenshot(path="output/ui-overview.png", animations="disabled")
        assert not errors
        browser.close()
