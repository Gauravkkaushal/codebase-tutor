const express = require("express");
const mongoose = require("mongoose");
const noteRoutes = require("./routes/notes");
const app = express();
app.use(express.json());
app.use("/api/notes", noteRoutes);
mongoose.connect(process.env.MONGO_URL).then(() => app.listen(5000));
