#!/usr/bin/env bash
# usage: e2e/search.sh "<query>" [screenshot-name]  -> prints understood pills + top results as JSON
q="$1"
playwright-cli fill "getByTestId('search-input')" "$q" --submit >/dev/null 2>&1
playwright-cli run-code "async page => { await page.waitForFunction(() => /hasil|Belum ada|gagal/.test(document.querySelector('[data-testid=status]').textContent + document.querySelector('[data-testid=results]').textContent) && !document.querySelector('.skeleton'), null, {timeout: 60000}); }" >/dev/null 2>&1
playwright-cli --raw eval "JSON.stringify({status: document.querySelector('[data-testid=status]').textContent, understood: [...document.querySelectorAll('#understood .pill')].map(p=>p.textContent), results: [...document.querySelectorAll('#results [data-testid=result-card]')].slice(0,5).map(c=>({f:c.dataset.fileId, conf:c.querySelector('[data-testid=confidence]').textContent, reason:c.querySelector('[data-testid=reason]').textContent, snip:(c.querySelector('.snippet')||{}).innerHTML?.slice(0,90), meta:c.querySelector('.meta').textContent})), weak: document.querySelectorAll('#weak [data-testid=result-card]').length, empty: !!document.querySelector('[data-testid=empty]'), error: !!document.querySelector('[data-testid=error]')})" 2>/dev/null | grep -v -e '^$' -e '║' -e '╔' -e '╚'
[ -n "$2" ] && playwright-cli screenshot --filename="e2e/cli-playwright/semantic-search/$2.png" >/dev/null 2>&1
exit 0
