const mongoose = require('mongoose');
const AutoIncrement = require('mongoose-sequence')(mongoose);

const ingredientSchema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: [true, 'Ingredient name is required'],
      unique: true,
      trim: true,
    },
    unit: {
      type: String,
      enum: ['g', 'kg', 'ml', 'l', 'piece', 'unit'],
      required: [true, 'Unit is required'],
    },
    currentStock: {
      type: Number,
      default: 0,
    },
    alertThreshold: {
      type: Number,
      default: 0,
    },
  },
  {
    timestamps: true,
  }
);

// Auto-increment plugin
ingredientSchema.plugin(AutoIncrement, { inc_field: 'id' });

const Ingredient = mongoose.model('Ingredient', ingredientSchema);

module.exports = Ingredient;