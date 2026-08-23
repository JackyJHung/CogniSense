// API client for CogniSense mobile. Talks to the SAME FastAPI backend
// used by the desktop app, so business logic stays centralized.

import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

// In production, replace with your deployed backend URL.
// On Android emulator, 10.0.2.2 maps to the host machine.
// On iOS simulator, localhost works.
const DEFAULT_BACKEND = 'http://10.0.2.2:8000';

let backendUrl = DEFAULT_BACKEND;
let accessToken = null;

export async function setBackendUrl(url) {
  backendUrl = url;
  await AsyncStorage.setItem('backendUrl', url);
}

export async function loadBackendUrl() {
  const stored = await AsyncStorage.getItem('backendUrl');
  if (stored) backendUrl = stored;
  return backendUrl;
}

async function setSession(data) {
  accessToken = data.access_token;
  await AsyncStorage.setItem('accessToken', data.access_token);
  await AsyncStorage.setItem('currentUser', JSON.stringify(data.user));
  return data.user;
}

export async function loadSession() {
  accessToken = await AsyncStorage.getItem('accessToken');
  return accessToken;
}

function client() {
  return axios.create({
    baseURL: backendUrl,
    timeout: 15000,
    headers: accessToken ? {Authorization: `Bearer ${accessToken}`} : {},
  });
}

// ---- Users ----
export async function signup(payload) {
  const { data } = await client().post('/users/signup', payload);
  return setSession(data);
}

export async function login(username, password) {
  const { data } = await client().post('/users/login', { username, password });
  return setSession(data);
}

export async function getCurrentUser() {
  const raw = await AsyncStorage.getItem('currentUser');
  return raw ? JSON.parse(raw) : null;
}

export async function logout() {
  accessToken = null;
  await AsyncStorage.multiRemove(['accessToken', 'currentUser']);
}

// ---- Check-ins ----
// The authenticated user is derived from the bearer token server-side, so no
// client-supplied user id is sent.
export async function morningCheckin(plannedActivities) {
  const { data } = await client().post('/checkins/morning', {
    planned_activities: plannedActivities,
  });
  return data;
}

export async function middayCheckin(morningId, whatDone, remainder, latencyMs) {
  const { data } = await client().post('/checkins/midday', {
    morning_checkin_id: morningId,
    what_user_has_done: whatDone,
    planned_remainder: remainder,
    response_latency_ms: latencyMs,
  });
  return data;
}

export async function eveningCheckin(morningId, recalled, responses) {
  const { data } = await client().post('/checkins/evening', {
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
