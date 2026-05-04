import React, { useState, useRef } from 'react';
import { View, Text, TextInput, Button, ScrollView, StyleSheet, Alert } from 'react-native';
import { getCurrentUser, middayCheckin } from '../api';
import Disclaimer from '../components/Disclaimer';

export default function MiddayScreen({ navigation }) {
  const [done, setDone] = useState('');
  const [remainder, setRemainder] = useState('');
  const startTime = useRef(Date.now());

  const submit = async () => {
    if (!done.trim()) {
      Alert.alert('Empty', 'Please describe what you have done so far.');
      return;
    }
    try {
      const user = await getCurrentUser();
      const latencyMs = Date.now() - startTime.current;
      const morningId = global.currentMorning?.id ?? null;
      await middayCheckin(user.id, morningId, done, remainder, latencyMs);
      Alert.alert('Recorded', 'Midday check-in saved.', [
        { text: 'OK', onPress: () => navigation.navigate('Dashboard') },
      ]);
    } catch (e) {
      Alert.alert('Error', e?.response?.data?.detail ?? e.message);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.header}>Midday check-in</Text>

      <Text>What have you done so far today?</Text>
      <TextInput style={styles.input} multiline value={done} onChangeText={setDone}
        placeholder="e.g. walked the dog, had breakfast..." />

      <Text>What do you still plan to do?</Text>
      <TextInput style={styles.input} multiline value={remainder} onChangeText={setRemainder}
        placeholder="e.g. call sister, read a chapter..." />

      <Button title="Submit" onPress={submit} />
      <Disclaimer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: '#fff' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 16 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 10,
           marginVertical: 10, minHeight: 80, textAlignVertical: 'top' },
});
