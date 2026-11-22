const express = require("express");
const router = express.Router();
const { listNotes, addNote } = require("../controllers/notes");
router.get("/", listNotes);
router.post("/add", addNote);
module.exports = router;
