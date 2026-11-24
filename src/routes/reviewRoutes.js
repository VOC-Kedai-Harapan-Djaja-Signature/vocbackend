import { Router } from 'express';
import { rateLimit } from 'express-rate-limit';
import { createPublicReview, createManualReview, listReviews, respondReview } from '../controllers/reviewController.js';
import { authenticate } from '../middlewares/authMiddleware.js';

const router = Router();

const reviewLimiter = rateLimit({
  windowMs: 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { message: 'Terlalu banyak kiriman. Coba lagi sebentar.' },
});

router.post('/reviews', reviewLimiter, createPublicReview);
router.post('/reviews/manual', authenticate, createManualReview);
router.get('/reviews', authenticate, listReviews);
router.patch('/reviews/:id/respond', authenticate, respondReview);

export default router;
