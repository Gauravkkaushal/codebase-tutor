const Note = require("../models/note");

const listNotes = async (req, res) => {
  const notes = await Note.find();
  res.status(200).json(notes);
};

const addNote = async (req, res) => {
  if (!req.body.text) {
    return res.status(400).json({ message: "text required" });
  }
  const note = new Note({ text: req.body.text });
  await note.save();
  res.status(201).json(note);
};

module.exports = { listNotes, addNote };
