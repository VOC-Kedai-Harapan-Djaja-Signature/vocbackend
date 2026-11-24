import { Router } from 'express';
import { listSuggestions, markSuggestionDone } from '../controllers/suggestionController.js';
import { authenticate, requireRole } from '../middlewares/authMiddleware.js';

const router = Router();

router.get('/suggestions', authenticate, listSuggestions);
router.patch('/suggestions/:id/complete', authenticate, requireRole('kepala_cabang'), markSuggestionDone);

export default router;