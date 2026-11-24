import { Router } from 'express';
import { showSettings, updateSettings } from '../controllers/settingController.js';
import { authenticate, requireRole } from '../middlewares/authMiddleware.js';

const router = Router();

router.get('/settings', authenticate, showSettings);
router.patch('/settings', authenticate, requireRole('kepala_cabang'), updateSettings);

export default router;