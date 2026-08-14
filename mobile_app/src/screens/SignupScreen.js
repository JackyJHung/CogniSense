import React, { useState } from 'react';
import { View, Text, TextInput, Button, ScrollView, StyleSheet, Alert } from 'react-native';
import { signup, login } from '../api';
import Disclaimer from '../components/Disclaimer';

const GENDERS = ['female', 'male', 'nonbinary', 'other', 'prefer_not'];
const RACES = ['white', 'black', 'hispanic', 'aapi', 'ai_an', 'other', 'prefer_not'];

export default function SignupScreen({ navigation }) {
  const [form, setForm] = useState({
    username: '', password: '', age: '',
    gender: 'female', race: 'white',
    wake_time: '07:00', sleep_time: '22:00',
  });
  const set = (k) => (v) => setForm({ ...form, [k]: v });

  const submit = async () => {
    try {
      const payload = {
        ...form,
        age: parseInt(form.age, 10),
        wake_time: `${form.wake_time}:00`,
        sleep_time: `${form.sleep_time}:00`,
      };
      await signup(payload);
      await login(form.username, form.password);
      navigation.replace('Dashboard');
    } catch (e) {
      Alert.alert('Sign-up failed', e?.response?.data?.detail ?? e.message);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <TextInput style={styles.input} placeholder="Username" value={form.username} onChangeText={set('username')} autoCapitalize="none" />
      <TextInput style={styles.input} placeholder="Password" value={form.password} onChangeText={set('password')} secureTextEntry />
      <TextInput style={styles.input} placeholder="Age" value={form.age} onChangeText={set('age')} keyboardType="numeric" />

      <Text style={styles.label}>Gender</Text>
      <View style={styles.row}>
        {GENDERS.map(g =>
          <Button key={g} title={g} color={form.gender === g ? '#4a5568' : '#a0aec0'} onPress={() => set('gender')(g)} />
        )}
      </View>

      <Text style={styles.label}>Race/Ethnicity</Text>
      <View style={styles.row}>
        {RACES.map(r =>
          <Button key={r} title={r} color={form.race === r ? '#4a5568' : '#a0aec0'} onPress={() => set('race')(r)} />
        )}
      </View>

      <TextInput style={styles.input} placeholder="Wake time (HH:MM)" value={form.wake_time} onChangeText={set('wake_time')} />
      <TextInput style={styles.input} placeholder="Sleep time (HH:MM)" value={form.sleep_time} onChangeText={set('sleep_time')} />

      <Button title="Create account" onPress={submit} />
      <Disclaimer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: '#fff' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 10, marginBottom: 10 },
  label: { fontWeight: 'bold', marginTop: 10, marginBottom: 6 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 6 },
});
