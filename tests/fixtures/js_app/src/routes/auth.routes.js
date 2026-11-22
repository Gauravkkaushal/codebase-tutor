const router = require('express').Router();
const { login, logout } = require('../controllers/auth.controller');
const { requireAuth } = require('../middleware/auth');

router.post('/login', login);
router.post('/logout', requireAuth, logout);

module.exports = router;
