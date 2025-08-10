const express = require("express");
const router = express.Router();
const { spawn } = require("child_process");
const Ingredient = require("../models/Ingredient");
const multer = require("multer");
const path = require("path");
const fs = require("fs");

const upload = multer({ dest: "uploads/" });

// Improved Python path detection
function getPythonPath() {
  // Try multiple possible Python paths
  const possiblePaths = [
    // Windows with .venv
    path.join(__dirname, "..", ".venv", "Scripts", "python.exe"),
    // Windows with venv
    path.join(__dirname, "..", "venv", "Scripts", "python.exe"),
    // Unix/Linux with .venv
    path.join(__dirname, "..", ".venv", "bin", "python"),
    // Unix/Linux with venv
    path.join(__dirname, "..", "venv", "bin", "python"),
    // System Python (Windows)
    "python.exe",
    // System Python (Unix/Linux/Mac)
    "python3",
    "python"
  ];

  for (const pythonPath of possiblePaths) {
    if (fs.existsSync(pythonPath) || !pythonPath.includes(path.sep)) {
      return pythonPath;
    }
  }

  // Default fallback
  return "python";
}

const pythonPath = getPythonPath();
const scriptPath = path.join(__dirname, "..", "assistant.py");

// Log the Python path being used
console.log(`Using Python path: ${pythonPath}`);
console.log(`Using script path: ${scriptPath}`);

async function fetchInventoryFromDB() {
  // Fetch live inventory from MongoDB (Ingredients collection)
  const ingredients = await Ingredient.find({});
  const inventory = {};
  ingredients.forEach((item) => {
    // Note: use currentStock or quantity field depending on your model
    // Here assuming 'currentStock' as per your Ingredient.js schema
    inventory[item.name.toLowerCase()] = item.currentStock ?? 0;
  });
  return inventory;
}

router.post("/ask", async (req, res) => {
  try {
    const { text } = req.body;
    if (!text || typeof text !== "string" || text.trim().length === 0) {
      return res.status(400).json({ error: "No text provided" });
    }

    const inventory = await fetchInventoryFromDB();

    // Pass the user text as a single argument to assistant.py
    // The Python script will fetch inventory live from DB itself, so no need to write inventory.json
    const python = spawn(pythonPath, [scriptPath, text]);

    let data = "";
    let errorOutput = "";

    python.stdout.on("data", (chunk) => {
      data += chunk.toString();
    });

    python.stderr.on("data", (err) => {
      errorOutput += err.toString();
      console.error("Python stderr:", err.toString());
    });

    python.on("error", (err) => {
      console.error("Failed to start Python process:", err);
      return res.status(500).json({
        error: "Failed to start Python process",
        details: err.message,
      });
    });

    python.on("close", (code) => {
      if (code !== 0 || errorOutput) {
        console.error("Python process error output:", errorOutput);
        return res.status(500).json({
          error: "Python process failed",
          code,
          stderr: errorOutput.trim(),
        });
      }
      res.json({ reply: data.trim() });
    });
  } catch (err) {
    console.error("Assistant error:", err);
    res.status(500).json({
      error: "Assistant failed",
      details: err.message,
    });
  }
});

router.post("/audio", upload.single("audio"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No audio file uploaded" });
    }

    const filePath = path.resolve(req.file.path);

    // Inventory is fetched live inside assistant.py, no need to write inventory.json here
    // But if your Python script expects inventory.json, you can write it here
    // For now, we assume direct DB access by Python

    const python = spawn(pythonPath, [scriptPath, "--audio", filePath]);

    let data = "";
    let errorOutput = "";

    python.stdout.on("data", (chunk) => {
      data += chunk.toString();
    });

    python.stderr.on("data", (err) => {
      errorOutput += err.toString();
      console.error("Python stderr:", err.toString());
    });

    python.on("close", (code) => {
      // Delete uploaded audio file after processing
      fs.unlink(filePath, (err) => {
        if (err) console.error("Failed to delete temp audio file:", err);
      });

      if (code !== 0 || errorOutput) {
        console.error("Python audio process error output:", errorOutput);
        return res.status(500).json({
          error: "Python audio process failed",
          code,
          stderr: errorOutput.trim(),
        });
      }
      res.json({ response: data.trim() });
    });

    python.on("error", (err) => {
      console.error("Failed to start Python audio process:", err);
      res.status(500).json({
        error: "Failed to start Python audio process",
        details: err.message,
      });
    });
  } catch (err) {
    console.error("Audio assistant error:", err);
    res.status(500).json({
      error: "Assistant audio processing failed",
      details: err.message,
    });
  }
});

module.exports = router;
