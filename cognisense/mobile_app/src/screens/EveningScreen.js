import React, { useState, useRef } from 'react';
import { View, Text, TextInput, Button, ScrollView, StyleSheet } from 'react-native';
import { getCurrentUser, eveningCheckin } from '../api';
import { showApiError } from '../utils';
import Disclaimer from '../components/Disclaimer';

export default function EveningScreen({ navigation }) {
  const morning = global.currentMorning;
  const [recalled, setRecalled] = useState('');
  const [answers, setAnswers] = useState(
    morning ? morning.presented_associations.map((a) => ({ id: a.id, answer: '' })) : []
  );
  const [result, setResult] = useState(null);
  const questionStartTimes = useRef({});

  if (!morning) {
    return (
      <View style={styles.container}>
        <Text style={styles.header}>No morning check-in</Text>
        <Text>Please complete a morning check-in first so we can grade your recall tonight.</Text>
        <View style={{ height: 14 }} />
        <Button title="Back to dashboard" onPress={() => navigation.navigate('Dashboard')} />
        <Disclaimer />
      </View>
    );
  }

  const updateAnswer = (id, text) => {
    // Record the time the user first focused on this answer as their "start"
    if (!questionStartTimes.current[id]) {
      questionStartTimes.current[id] = Date.now();
    }
    setAnswers((prev) => prev.map((a) => (a.id === id ? { ...a, answer: text } : a)));
  };

  const submit = async () => {
    const now = Date.now();
    const responses = answers.map((a) => ({
      association_id: a.id,
      user_answer: a.answer,
      response_latency_ms: questionStartTimes.current[a.id]
        ? now - questionStartTimes.current[a.id]
        : 5000,
    }));

    try {
      const user = await getCurrentUser();
      const ev = await eveningCheckin(user.id, morning.id, recalled, responses);
      setResult(ev);
    } catch (e) {
      showApiError(e);
    }
  };

  if (result) {
    return (
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.header}>Daily results</Text>
        <Text style={styles.line}>Daily cognitive score:       {result.daily_cognitive_score?.toFixed(2)} / 1.00</Text>
        <Text style={styles.line}>Image-association accuracy:  {(result.association_accuracy * 100).toFixed(0)}%</Text>
        <Text style={styles.line}>Activity-recall accuracy:    {((result.activity_recall_accuracy ?? 0) * 100).toFixed(0)}%</Text>
        <Text style={styles.line}>Avg. response latency:       {result.avg_response_latency_ms} ms</Text>
        <Text style={styles.line}>Speech biomarker:            {(result.speech_biomarker_score ?? 0).toFixed(2)}</Text>
        <View style={{ height: 16 }} />
        <Button title="View risk report" onPress={() => navigation.navigate('Report')} />
        <View style={{ height: 10 }} />
        <Button title="Back to dashboard" onPress={() => navigation.navigate('Dashboard')} />
        <Disclaimer />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.header}>Evening check-in</Text>

      <Text>What do you remember doing today?</Text>
      <TextInput
        style={styles.input}
        multiline
        value={recalled}
        onChangeText={setRecalled}
        placeholder="Describe your day..."
      />

      <Text style={styles.sub}>For each cue word, type the object you were shown this morning:</Text>
      {morning.presented_associations.map((a) => (
        <View key={a.id} style={styles.qRow}>
          <Text style={styles.cue}>Cue: {a.cue_word}</Text>
          <TextInput
            style={styles.qInput}
            value={answers.find((x) => x.id === a.id)?.answer ?? ''}
            onChangeText={(text) => updateAnswer(a.id, text)}
            onFocus={() => {
              if (!questionStartTimes.current[a.id]) {
                questionStartTimes.current[a.id] = Date.now();
              }
            }}
            autoCapitalize="none"
          />
        </View>
      ))}

      <View style={{ height: 10 }} />
      <Button title="Submit evening check-in" onPress={submit} />
      <Disclaimer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: '#fff' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 12 },
  sub: { marginTop: 16, marginBottom: 8, fontWeight: '600' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 10,
           marginVertical: 10, minHeight: 100, textAlignVertical: 'top' },
  qRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  cue: { width: 130, fontWeight: 'bold' },
  qInput: { flex: 1, borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 8 },
  line: { fontFamily: 'Courier', fontSize: 14, marginBottom: 6 },
});
