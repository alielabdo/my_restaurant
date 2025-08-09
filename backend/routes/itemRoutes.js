const express = require('express');
const router = express.Router();
const { protect } = require('../middlewares/authMiddleware');
const {
  createItem,
  getItems,
  getItemById,
  updateItem,
  deleteItem
} = require('../controllers/itemsController');

router.post('/', protect, createItem);
router.get('/', protect, getItems);
router.get('/:id', protect, getItemById);
router.put('/:id', protect, updateItem);
router.delete('/:id', protect, deleteItem);

module.exports = router;