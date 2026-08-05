import { db } from '../db/database';

const SESSION_KEY = 'godown_camera_app_session';

export async function verifyUserPin(pin: string): Promise<boolean> {
  const user = await db.users.toCollection().first();
  if (!user) return true; // If no auth configured, allow access
  if (!user.authEnabled) return true;
  return user.pinHash === pin;
}

export async function updateUserPin(newPin: string): Promise<void> {
  const user = await db.users.toCollection().first();
  if (user) {
    await db.users.update(user.id!, { pinHash: newPin, authEnabled: true });
  } else {
    await db.users.add({
      username: 'admin',
      pinHash: newPin,
      authEnabled: true,
      biometricEnabled: false,
      lastLogin: new Date().toISOString()
    });
  }
}

export function setLocalSessionUnlocked(unlocked: boolean): void {
  if (unlocked) {
    sessionStorage.setItem(SESSION_KEY, 'unlocked');
  } else {
    sessionStorage.removeItem(SESSION_KEY);
  }
}

export function isSessionUnlocked(): boolean {
  return sessionStorage.getItem(SESSION_KEY) === 'unlocked';
}

export async function exportCameraConfigJson(): Promise<string> {
  const cameras = await db.cameras.toArray();
  const exportData = {
    app: 'GodownCameraMobileApp',
    version: '1.0.0',
    exportedAt: new Date().toISOString(),
    cameras
  };
  return JSON.stringify(exportData, null, 2);
}

export async function importCameraConfigJson(jsonStr: string): Promise<number> {
  try {
    const data = JSON.parse(jsonStr);
    if (!data.cameras || !Array.isArray(data.cameras)) {
      throw new Error('Invalid backup file format');
    }
    await db.cameras.clear();
    const now = new Date().toISOString();
    const sanitizedCameras = data.cameras.map((c: any) => ({
      ...c,
      createdAt: c.createdAt || now,
      updatedAt: now
    }));
    await db.cameras.bulkAdd(sanitizedCameras);
    return sanitizedCameras.length;
  } catch (err) {
    console.error('Import failed:', err);
    throw err;
  }
}
