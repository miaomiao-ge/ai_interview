import assert from 'node:assert/strict';

import { getAuthModeConfig, getEmailCodePurpose } from '../frontend/user/js/auth_state.js';

const config = getAuthModeConfig('forgot');

assert.equal(config.showCodeInput, true);
assert.equal(config.showUsernameInput, false);
assert.equal(config.sendCodePurpose, 'forgot');
assert.match(config.primaryButtonText.zh, /重置/);

assert.equal(getEmailCodePurpose('register'), 'register');
assert.equal(getEmailCodePurpose('forgot'), 'forgot');
assert.equal(getEmailCodePurpose('login'), 'forgot');
