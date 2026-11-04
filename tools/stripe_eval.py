"""Opt-in Stripe sandbox eval. Never uses live keys or the application's data directory."""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = 'http://127.0.0.1:18765'
DONOR = {'name': 'Teste Integracao', 'email': 'stripe-eval@example.com', 'cpf': '52998224725'}


def wait_for(check, description, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.2)
    raise AssertionError('Timed out: ' + description)


def main():
    credentials = {**dotenv_values(ROOT / 'backend/.env'), **os.environ}
    key = credentials.get('STRIPE_SECRET_KEY', '')
    assert key.startswith(('sk_test_', 'rk_test_')), 'Configure a Stripe TEST key'
    executable = shutil.which('stripe.cmd') or shutil.which('stripe')
    assert executable, 'Install Stripe CLI first'
    cli_env = {**os.environ, 'STRIPE_API_KEY': key}
    api_version = credentials.get('STRIPE_API_VERSION', '2026-10-28.endive')
    webhooks = []
    sessions = []
    subscriptions = []
    listener = None
    server = None
    server_thread = None
    with tempfile.TemporaryDirectory(prefix='fundo-stripe-eval-') as temporary:
        cli = [executable, '--config', str(Path(temporary) / 'stripe.toml')]

        def stripe(*args):
            parameters = list(args)
            if args[0] in {'get', 'post', 'delete'}:
                parameters += ['--stripe-version', api_version]
            result = subprocess.run(cli + parameters, env=cli_env, capture_output=True, text=True, timeout=45)
            assert result.returncode == 0, 'Stripe CLI command failed: ' + ' '.join(args[:2])
            if args[0] in {'get', 'post', 'delete'}:
                data = json.loads(result.stdout)
                error = data.get('error', {})
                assert not error, 'Stripe API error: ' + str(error.get('code') or error.get('param') or error.get('type'))
                return data
            return result.stdout

        secret = re.search(r'whsec_[A-Za-z0-9]+', stripe('listen', '--print-secret')).group()
        os.environ.update(STRIPE_SECRET_KEY=key, STRIPE_WEBHOOK_SECRET=secret,
                          STRIPE_API_VERSION=api_version,
                          DATA_DIR=temporary, EMAIL_ENABLED='false', STORAGE_BACKEND='local',
                          APP_ENV='development', PUBLIC_BASE_URL=BASE, PYTHON_DOTENV_DISABLED='1')
        from backend.app.main import app, service

        # Keep signed deliveries only in memory so exact retries exercise the real endpoint.
        @app.middleware('http')
        async def capture(request, call_next):
            body = await request.body() if request.url.path == '/api/webhooks/stripe' else None
            response = await call_next(request)
            if body is not None and request.headers.get('stripe-signature'):
                webhooks.append((body, {'Stripe-Signature': request.headers['stripe-signature']}, response.status_code))
            return response

        try:
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18765, log_level='error', access_log=False))
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()
            wait_for(lambda: server.started, 'local application startup', 10)
            logging.getLogger('fundo.requests').disabled = True
            listener = subprocess.Popen(cli + ['listen', '--latest', '--events',
                'checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,invoice.payment_succeeded,invoice.payment_failed,customer.subscription.deleted',
                '--forward-to', BASE + '/api/webhooks/stripe'], env=cli_env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            ready = queue.Queue()

            def read_listener():
                for line in listener.stdout:
                    if 'Ready!' in line:
                        ready.put(line)

            threading.Thread(target=read_listener, daemon=True).start()
            line = ready.get(timeout=30)
            assert service.settings.stripe_api_version in line, 'CLI/API versions differ; align STRIPE_API_VERSION'
            print('PASS: Stripe CLI connected with matching API version', flush=True)
            with httpx.Client(base_url=BASE, timeout=30) as client, sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='chrome', headless=True)
                try:
                    assert client.post('/api/webhooks/stripe', content=b'{}').status_code == 401
                    invalid = {'donor': {**DONOR, 'cpf': '11111111111'}, 'method': 'card', 'program': 'geral', 'amount_cents': 1000}
                    assert client.post('/api/donations/intents', json=invalid).status_code == 422
                    invalid['donor'] = DONOR
                    invalid['method'] = 'pix_automatico'
                    assert client.post('/api/donations/intents', json=invalid).status_code == 422
                    print('PASS: invalid CPF and unsupported Pix Automatico rejected before checkout', flush=True)
                    for method, outcome in (('card', 'paid'), ('card_recurring', 'paid'), ('pix', 'paid'), ('pix', 'expired')):
                        context = browser.new_context(locale='pt-BR')
                        page = context.new_page()
                        page.goto(BASE + '/como-apoiar/')
                        page.locator('#customAmount').fill('10')
                        page.locator(f'input[name=method][value={method}]').check()
                        page.locator('button[type=submit]').click()
                        page.locator('input[name=program][value=geral]').check()
                        page.locator('#donorName').fill(DONOR['name'])
                        page.locator('#donorEmail').fill(DONOR['email'])
                        page.locator('#donorCpf').fill(DONOR['cpf'])
                        page.locator('#privacyAcknowledgement').check()
                        with page.expect_response(lambda r: r.url.endswith('/api/donations/intents') and r.request.method == 'POST') as created:
                            page.locator('button[type=submit]').click()
                        response = created.value
                        assert response.status == 201, f'{method}: intent HTTP {response.status}'
                        intent = response.json()
                        session_id = service.pending.get(intent['donation_id']).provider_payment_id
                        sessions.append(session_id)
                        session = stripe('get', '/v1/checkout/sessions/' + session_id)
                        assert session['livemode'] is False
                        assert session['mode'] == ('subscription' if method == 'card_recurring' else 'payment')
                        assert session['currency'] == 'brl' and session['amount_total'] == 1000
                        assert session['payment_method_types'] == ['pix' if method == 'pix' else 'card']
                        assert all(value not in json.dumps(session['metadata']) for value in DONOR.values())
                        headers = {'X-Donation-Token': intent['status_token']}
                        status_path = '/api/donations/' + intent['donation_id'] + '/status'
                        assert client.get(status_path, headers=headers).json()['status'] == 'pending'
                        assert not service.confirmed_donations.contains(intent['donation_id'])
                        replay = client.post('/api/donations/intents', content=response.request.post_data,
                            headers={'Content-Type': 'application/json', 'X-Idempotency-Key': response.request.headers['x-idempotency-key']})
                        assert replay.status_code == 201 and replay.json() == intent, 'Intent retry created a second checkout'
                        print('PASS:', method, 'form, hosted session, BRL amount, method, pending and no donor persistence', flush=True)
                        page.wait_for_url('https://checkout.stripe.com/**', timeout=20000)
                        if outcome == 'expired':
                            page.goto(session['cancel_url'])
                            page.locator('#paymentStage').wait_for(state='visible')
                            assert page.locator('#successStage').is_hidden()
                            assert client.get(status_path, headers=headers).json()['status'] == 'pending'
                            stripe('post', '/v1/checkout/sessions/' + session_id + '/expire', '--confirm')
                            page.locator('#restartContribution').wait_for(state='visible', timeout=45000)
                            assert client.get(status_path, headers=headers).json()['status'] == 'failed'
                            assert not service.confirmed_donations.contains(intent['donation_id'])
                            page.locator('#restartContribution').click()
                            page.locator('#contributionStep').wait_for(state='visible')
                            sessions.remove(session_id)
                            print('PASS: cancellation is not payment; signed expiration permits a new attempt without saving PII', flush=True)
                            context.close()
                            continue
                        forged = browser.new_page()
                        forged.goto(session['success_url'])
                        forged.locator('#formStatus').wait_for(state='visible')
                        assert forged.locator('#successStage').is_hidden(), 'Browser return incorrectly confirmed payment'
                        forged.close()
                        page.locator('#email').fill('succeed_immediately@example.com' if method == 'pix' else DONOR['email'])
                        if method != 'pix':
                            # Test card details are entered exclusively on Stripe's hosted origin.
                            page.locator('#cardNumber').fill('4242424242424242')
                            page.locator('#cardExpiry').fill('12/30')
                            page.locator('#cardCvc').fill('123')
                            page.locator('#billingName').fill(DONOR['name'])
                            page.locator('#billingCountry').select_option('BR')
                            if method == 'card':
                                page.locator('#cardNumber').fill('4000000000000002')
                                page.locator('button[type=submit]').click()
                                page.get_by_text(re.compile('recusad|declin', re.I)).first.wait_for(timeout=30000)
                                assert client.get(status_path, headers=headers).json()['status'] == 'pending'
                                assert not service.confirmed_donations.contains(intent['donation_id'])
                                page.locator('#cardNumber').fill('4242424242424242')
                                print('PASS: declined card remains unpaid and permits retry at Stripe', flush=True)
                        page.locator('button[type=submit]').click()
                        page.wait_for_url(BASE + '/como-apoiar/**', timeout=60000)
                        page.locator('#successStage').wait_for(state='visible', timeout=45000)
                        state = client.get(status_path, headers=headers).json()
                        assert state['status'] == 'paid' and state['persisted'] is True
                        assert 'donation_id=' not in page.url
                        record = service.confirmed_donations.get_model(intent['donation_id'])
                        assert record.donor_cpf == DONOR['cpf'] and record.amount_cents == 1000
                        session = stripe('get', '/v1/checkout/sessions/' + session_id)
                        if session.get('subscription'):
                            subscriptions.append(session['subscription'])
                            subscription_id = session['subscription']
                            # A separate paid invoice tests recurrence without changing the billing schedule.
                            renewed = stripe('post', '/v1/invoices', '--confirm',
                                '-d', 'customer=' + session['customer'], '-d', 'subscription=' + subscription_id)
                            renewal_id = renewed['id']
                            stripe('post', '/v1/invoiceitems', '--confirm', '-d', 'customer=' + session['customer'],
                                '-d', 'invoice=' + renewal_id, '-d', 'amount=1000', '-d', 'currency=brl')
                            stripe('post', '/v1/invoices/' + renewal_id + '/finalize', '--confirm')
                            paid_invoice = stripe('post', '/v1/invoices/' + renewal_id + '/pay', '--confirm')
                            assert paid_invoice['status'] == 'paid' and paid_invoice['amount_paid'] == 1000
                            assert renewal_id != session['invoice'], 'A second subscription invoice was not generated'
                            wait_for(lambda: service.recurring_payments.contains(renewal_id), 'second paid subscription invoice')
                            assert len(service.recurring_payments.records()) == 2
                            stripe('delete', '/v1/subscriptions/' + subscription_id, '--confirm')
                            subscriptions.remove(subscription_id)
                            wait_for(lambda: any(json.loads(body).get('type') == 'customer.subscription.deleted' and subscription_id.encode() in body
                                                 for body, _, code in webhooks if code == 200), 'subscription cancellation webhook')
                            assert client.get(status_path, headers=headers).json()['status'] == 'paid'
                            print('PASS: second subscription invoice recorded; cancellation preserves paid history', flush=True)
                        matching = [(body, signed_headers) for body, signed_headers, code in webhooks
                                    if intent['donation_id'] in body.decode() and code == 200]
                        assert matching, 'No signed application webhook received'
                        for body, signed_headers in matching:
                            assert client.post('/api/webhooks/stripe', content=body, headers=signed_headers).status_code == 200
                            assert client.post('/api/webhooks/stripe', content=body + b' ', headers=signed_headers).status_code == 401
                        if method == 'card_recurring':
                            assert len(service.recurring_payments.records()) == 2, 'Invoice replay duplicated a payment'
                        confirmed = Path(temporary) / 'confirmed_donations.jsonl'
                        assert sum(json.loads(line)['donation_id'] == intent['donation_id'] for line in confirmed.read_text().splitlines()) == 1
                        sessions.remove(session_id)
                        print('PASS:', method, 'real test payment, signed webhook, browser success, duplicate and tamper protection, donor saved exactly once', flush=True)
                        context.close()
                    assert webhooks and all(status in {200, 401} for _, _, status in webhooks), 'A valid webhook was rejected'
                    print('PASS: all signed webhooks accepted', flush=True)
                finally:
                    browser.close()
        finally:
            for session_id in sessions:
                try:
                    session = stripe('get', '/v1/checkout/sessions/' + session_id)
                    if session.get('subscription'):
                        subscriptions.append(session['subscription'])
                    if session['status'] == 'open':
                        stripe('post', '/v1/checkout/sessions/' + session_id + '/expire', '--confirm')
                except Exception:
                    print('CLEANUP FAILED: test checkout expiration', flush=True)
            for subscription_id in set(subscriptions):
                try:
                    stripe('delete', '/v1/subscriptions/' + subscription_id, '--confirm')
                except Exception:
                    print('CLEANUP FAILED: test subscription cancellation', flush=True)
            if listener is not None:
                listener.terminate()
                listener.wait(timeout=10)
            if server is not None:
                server.should_exit = True
            if server_thread is not None:
                server_thread.join(timeout=10)


if __name__ == '__main__':
    main()
