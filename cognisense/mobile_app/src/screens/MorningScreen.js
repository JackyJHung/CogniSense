import React, { useState } from 'react';
import { View, Text, TextInput, Button, ScrollView, StyleSheet, Alert } from 'react-native';
import { morningCheckin } from '../api';
import Disclaimer from '../components/Disclaimer';

export default function MorningScreen({ navigation }) {
  const [plans, setPlans] = useState('');
  const [associations, setAssociations] = useState(null);

  const submit = async () => {
    if (!plans.trim()) {
      Alert.alert('Empty', 'Please enter at least one activity.');
      return;
    }
    try {
      const result = await morningCheckin(plans);
      // Cache morning check-in ID for the evening flow
      global.currentMorning = result;
      setAssociations(result.presented_associations);
    } catch (e) {
      Alert.alert('Error', e?.response?.data?.detail ?? e.message);
    }
  };

  if (associations) {
    return (
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.header}>Remember these</Text>
        <Text style={styles.sub}>You'll be tested tonight.</Text>
        {associations.map((a) => (
          <View key={a.id} style={styles.card}>
            <Text style={styles.cue}>Cue: "{a.cue_word}"</Text>
            <Text style={styles.obj}>Object: {a.object_name}</Text>
            <Text style={styles.path}>[image: {a.image_path}]</Text>
          </View>
        ))}
        <Button title="Back to dashboard" onPress={() => navigation.navigate('Dashboard')} />
        <Disclaimer />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.header}>Morning check-in</Text>
      <Text>What do you plan to do today? (one per line)</Text>
      <TextInput
        style={styles.input}
        multiline
        numberOfLines={6}
        value={plans}
        onChangeText={setPlans}
        placeholder="e.g. walk the dog, call Mom, buy groceries..."
      />
      <Button title="Submit & see associations" onPress={submit} />
      <Disclaimer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: '#fff' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 8 },
  sub: { color: '#666', marginBottom: 16 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 10,
           marginVertical: 10, minHeight: 120, textAlignVertical: 'top' },
  card: { padding: 12, marginBottom: 10, backgroundColor: '#f7fafc', borderRadius: 6,
          borderWidth: 1, borderColor: '#e2e8f0' },
  cue: { fontSize: 16, fontWeight: 'bold' },
  obj: { fontSize: 16, marginTop: 4 },
  path: { fontSize: 11, fontStyle: 'italic', color: '#888', marginTop: 4 },
});
