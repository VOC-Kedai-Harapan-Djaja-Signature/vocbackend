import { Router } from 'express';
import { createWeeklyReport, getLatestReport } from '../controllers/reportController.js';
import { authenticate } from '../middlewares/authMiddleware.js';

const router = Router();

router.post('/reports/weekly', authenticate, createWeeklyReport);
router.get('/reports/weekly/latest', authenticate, getLatestReport);

export default router;