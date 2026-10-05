// k6 performance smoke test for POST /v1/payments/split
//
// Counterpart of tests/test_performance_smoke.py: the pytest version guards
// against algorithmic regressions in CI, this one runs against a deployed
// environment with real network and real provider latency.
//
//   k6 run -e BASE_URL=https://staging.example.com perf/k6-split-smoke.js
import http from 'k6/http';
import { check } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

export const options = {
  stages: [
    { duration: '30s', target: 20 },  // ramp up
    { duration: '1m',  target: 20 },  // steady state
    { duration: '20s', target: 0  },  // ramp down
  ],
  thresholds: {
    // A breach fails the CI step, so the release evidence is collected
    // automatically instead of being judged by eye.
    'http_req_duration{endpoint:split}': ['p(95)<2500'],
    'http_req_failed': ['rate<0.005'],
    'checks': ['rate>0.99'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  const payload = JSON.stringify({
    order_id: `ord_${uuidv4()}`,
    currency: 'TRY',
    total: '100.00',
    splits: [
      { instrument: 'card', token: 'tok_load', amount: '60.00' },
      { instrument: 'wallet', wallet_id: 'w_load', amount: '40.00' },
    ],
  });

  const res = http.post(`${BASE_URL}/v1/payments/split`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': uuidv4(),   // a fresh key per request: no replay
      'X-User-Id': 'user_1',
    },
    tags: { endpoint: 'split' },
  });

  check(res, {
    'accepted (201)': (r) => r.status === 201,
    'not a gateway timeout': (r) => r.status !== 504,
    'response carries a payment id': (r) => r.json('payment_id') !== undefined,
  });
}
