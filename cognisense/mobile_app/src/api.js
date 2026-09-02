// API client for CogniSense mobile. Talks to the SAME FastAPI backend
// used by the desktop app, so business logic stays centralized.

import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

// In production, replace with your deployed backend URL.
// On Android emulator, 10.0.2.2 maps to the host machine.
// On iOS simulator, localhost works.
const DEFAULT_BACKEND = 'http://10.0.2.2:8000';

let backendUrl = DEFAULT_BACKEND;

export async function setBackendUrl(url) {
  backendUrl = url;
  await AsyncStorage.setItem('backendUrl', url);
}

export async function loadBackendUrl() {
  const stored = await AsyncStorage.getItem('backendUrl');
  if (stored) backendUrl = stored;
  return backendUrl;
}

function client() {
  return axios.create({
    baseURL: backendUrl,
    timeout: 15000,
  });
}

// ---- Users ----
export async function signup(payload) {
  const { data } = await client().post('/users/signup', payload);
  return data;
}

export async function login(username, password) {
  const { data } = await client().post('/users/login', { username, password });
  await AsyncStorage.setItem('currentUser', JSON.stringify(data));
  return data;
}

export async function getCurrentUser() {
  const raw = await AsyncStorage.getItem('currentUser');
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    console.warn('Stored currentUser is corrupt; clearing it', e);
    await AsyncStorage.removeItem('currentUser');
    return null;
  }
}

export async function logout() {
  await AsyncStorage.removeItem('currentUser');
}

// ---- Check-ins ----
export async function morningCheckin(userId, plannedActivities) {
  const { data } = await client().post('/checkins/morning', {
    user_id: userId,
    planned_activities: plannedActivities,
  });
  return data;
}

export async function middayCheckin(userId, morningId, whatDone, remainder, latencyMs) {
  const { data } = await client().post('/checkins/midday', {
    user_id: userId,
    morning_checkin_id: morningId,
    what_user_has_done: whatDone,
    planned_remainder: remainder,
    response_latency_ms: latencyMs,
  });
  return data;
}

export async function eveningCheckin(userId, morningId, recalled, responses) {
  const { data } = await client().post('/checkins/evening', {
    user_id: userId,
    morning_checkin_id: morningId,
    recalled_activities: recalled,
    association_responses: responses,
  });
  return data;
}

// ---- Reports ----
export async function getRiskComparison(userId, windowDays = 14) {
  const { data } = await client().get(
    `/reports/risk-comparison/${userId}?window_days=${windowDays}`,
  );
  return data;
}

export async function getDailySuggestions(userId) {
  const { data } = await client().get(`/reports/daily-suggestions/${userId}`);
  return data;
}

export async function getTrend(userId, days = 30) {
  const { data } = await client().get(`/reports/trend/${userId}?days=${days}`);
  return data;
}
