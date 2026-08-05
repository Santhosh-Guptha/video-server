import Dexie, { type Table } from 'dexie';
import type { CameraConfig, UserAuth } from '../types/camera';

export class CameraAppDatabase extends Dexie {
  cameras!: Table<CameraConfig, number>;
  users!: Table<UserAuth, number>;

  constructor() {
    super('GodownCameraMobileDB');
    this.version(1).stores({
      cameras: '++id, name, location, localIp, remoteHost, nvrBrand',
      users: '++id, username, pinHash'
    });
  }
}

export const db = new CameraAppDatabase();

/**
 * Seeds the database with the user's NVR configuration (182.76.136.44:8554).
 */
export async function seedInitialData() {
  const cameraCount = await db.cameras.count();
  if (cameraCount === 0) {
    const now = new Date().toISOString();
    await db.cameras.bulkAdd([
      {
        name: 'NVRTEST01 - Channel 101 (HD)',
        location: 'Office / Godown Zone 1',
        localIp: '182.76.136.44',
        remoteHost: '182.76.136.44',
        rtspPort: 8554,
        httpPort: 80,
        username: 'admin',
        password: 'xx2317xx2317',
        channel: 1, // Channel ID 101
        nvrBrand: 'hikvision',
        streamQuality: 'main',
        isNvr: true,
        activeMode: 'remote',
        createdAt: now,
        updatedAt: now
      },
      {
        name: 'NVRTEST01 - Channel 201 (HD)',
        location: 'Office / Godown Zone 2',
        localIp: '182.76.136.44',
        remoteHost: '182.76.136.44',
        rtspPort: 8554,
        httpPort: 80,
        username: 'admin',
        password: 'xx2317xx2317',
        channel: 2, // Channel ID 201
        nvrBrand: 'hikvision',
        streamQuality: 'main',
        isNvr: true,
        activeMode: 'remote',
        createdAt: now,
        updatedAt: now
      },
      {
        name: 'NVRTEST01 - Channel 401 (Sub)',
        location: 'Office / Perimeter Zone 4',
        localIp: '182.76.136.44',
        remoteHost: '182.76.136.44',
        rtspPort: 8554,
        httpPort: 80,
        username: 'admin',
        password: 'xx2317xx2317',
        channel: 4, // Channel ID 401
        nvrBrand: 'hikvision',
        streamQuality: 'sub',
        isNvr: true,
        activeMode: 'remote',
        createdAt: now,
        updatedAt: now
      }
    ]);
  }

  const userCount = await db.users.count();
  if (userCount === 0) {
    // Default user PIN 1234
    await db.users.add({
      username: 'admin',
      pinHash: '1234',
      authEnabled: true,
      biometricEnabled: false,
      lastLogin: new Date().toISOString()
    });
  }
}

/**
 * Resets and overwrites the camera table with the user's explicit NVR config payload.
 */
export async function loadUserNvrConfig() {
  const now = new Date().toISOString();
  await db.cameras.clear();
  await db.cameras.bulkAdd([
    {
      name: 'NVRTEST01 - Channel 101',
      location: 'Static Channel 101 (H.265 1080p)',
      localIp: '182.76.136.44',
      remoteHost: '182.76.136.44',
      rtspPort: 8554,
      httpPort: 80,
      username: 'admin',
      password: 'xx2317xx2317',
      channel: 1,
      nvrBrand: 'hikvision',
      streamQuality: 'main',
      isNvr: true,
      activeMode: 'remote',
      createdAt: now,
      updatedAt: now
    },
    {
      name: 'NVRTEST01 - Channel 201',
      location: 'Static Channel 201 (H.265 1080p)',
      localIp: '182.76.136.44',
      remoteHost: '182.76.136.44',
      rtspPort: 8554,
      httpPort: 80,
      username: 'admin',
      password: 'xx2317xx2317',
      channel: 2,
      nvrBrand: 'hikvision',
      streamQuality: 'main',
      isNvr: true,
      activeMode: 'remote',
      createdAt: now,
      updatedAt: now
    },
    {
      name: 'NVRTEST01 - Channel 401',
      location: 'Static Channel 401 (H.264 480p)',
      localIp: '182.76.136.44',
      remoteHost: '182.76.136.44',
      rtspPort: 8554,
      httpPort: 80,
      username: 'admin',
      password: 'xx2317xx2317',
      channel: 4,
      nvrBrand: 'hikvision',
      streamQuality: 'sub',
      isNvr: true,
      activeMode: 'remote',
      createdAt: now,
      updatedAt: now
    }
  ]);
}
