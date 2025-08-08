const express = require("express");
const router = express.Router();
const { spawn } = require("child_process");
const Ingredient = require("../models/Ingredient");
const fs = require("fs");
const multer = require("multer");
const path = require("path");
const upload = multer({ dest: "uploads/" });

router.post("/ask", async (req, res) => {
  try {
    const { text } = req.body;

    // Fetch inventory from MongoDB
    const ingredients = await Ingredient.find({});
    const inventory = {};
    ingredients.forEach(item => {
      inventory[item.name.toLowerCase()] = item.quantity;
    });

    // Save inventory temporarily as JSON
    fs.writeFileSync("inventory.json", JSON.stringify(inventory, null, 2));

    // Run the assistant model
    const python = spawn("D:/laser/backend/.venv/Scripts/python.exe", ["query.py", text]);

    let data = "";
    python.stdout.on("data", chunk => data += chunk.toString());
    python.stderr.on("data", err => console.error("Python error:", err.toString()));
    python.on("close", () => res.json({ reply: data.trim() }));

  } catch (err) {
    console.error("Assistant error:", err);
    res.status(500).json({ error: "Assistant failed." });
  }
});

router.post("/audio", upload.single("audio"), async (req, res) => {
  const filePath = path.resolve(req.file.path);
  const ingredients = await Ingredient.find({});
  const inventory = {};
  ingredients.forEach(item => {
    inventory[item.name.toLowerCase()] = item.quantity;
  });

  fs.writeFileSync("inventory.json", JSON.stringify(inventory, null, 2));

  const py = spawn("D:/laser/backend/.venv/Scripts/python.exe", ["query.py", "--audio", filePath]);

  let data = "";
  py.stdout.on("data", chunk => data += chunk);
  py.stderr.on("data", err => console.error("Python error:", err.toString()));
  py.on("close", () => {
    fs.unlink(filePath, () => {});
    res.json({ response: data.trim() });
  });
});

module.exports = router;
