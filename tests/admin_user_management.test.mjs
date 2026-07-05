import assert from 'node:assert/strict';
import { canSeeAdminUsersTab, normalizeAdminRow } from '../frontend/admin/js/admin_api.js';

assert.equal(canSeeAdminUsersTab('super_admin'), true);
assert.equal(canSeeAdminUsersTab('admin'), false);
assert.deepEqual(
  normalizeAdminRow({
    username: 'ops01',
    display_name: '',
    email: '',
    role: 'admin',
    status: 'disabled',
  }),
  {
    id: null,
    username: 'ops01',
    display_name: '-',
    email: '-',
    role: 'admin',
    status: 'disabled',
    last_login_at: '-',
    created_at: '-',
    created_by: null,
    raw_display_name: '',
    raw_email: '',
  },
);

console.log('admin user management helpers ok');
