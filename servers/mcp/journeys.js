// Runs every journey at a constant arrival rate, so a slow or stuck system cannot slow the
// measurement down. The config comes from the JSON file in CONFIG_FILE, written by measure_journeys.
import http from 'k6/http';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';

const config = JSON.parse(open(__ENV.CONFIG_FILE));

const journeyOk = new Counter('journey_ok');
const journeyFailed = new Counter('journey_failed');
const journeyDuration = new Trend('journey_duration', true);

export const options = {
    discardResponseBodies: true,
    scenarios: Object.fromEntries(Object.keys(config.journeys).map((name) => [name, {
        executor: 'constant-arrival-rate',
        rate: config.new_users_per_second,
        timeUnit: '1s',
        duration: `${config.measure_for_s}s`,
        // All of them up front: starting users mid-run would happen just when the system gets stuck.
        preAllocatedVUs: config.concurrent_users[name],
        maxVUs: config.concurrent_users[name],
        gracefulStop: `${config.fail_request_after_s}s`,
        exec: 'run',
        env: { JOURNEY: name },
    }])),
};

export function run() {
    const name = __ENV.JOURNEY;
    const started = Date.now();
    // The second in which this user arrived, counted from the start of the measurement.
    const second = String(Math.floor((started - exec.scenario.startTime) / 1000));
    const jar = new http.CookieJar();
    let error = null;
    for (const step of config.journeys[name]) {
        const res = http.request(step.method, config.base_url + step.path, step.form || null,
            { jar, timeout: `${config.fail_request_after_s}s`, tags: { journey: name } });
        if (res.status === 0) {
            error = res.error_code === 1050 ? 'timeout' : `network error ${res.error_code}`;
            break;
        }
        if (res.status >= 400) {
            error = `http ${res.status}`;
            break;
        }
    }
    const tags = { journey: name, second };
    journeyDuration.add(Date.now() - started, tags);
    if (error === null) {
        journeyOk.add(1, tags);
    } else {
        journeyFailed.add(1, { ...tags, error });
    }
}