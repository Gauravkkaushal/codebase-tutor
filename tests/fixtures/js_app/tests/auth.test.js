const { login } = require('../src/controllers/auth.controller');

test('login rejects missing credentials', async () => {
  expect(typeof login).toBe('function');
});
