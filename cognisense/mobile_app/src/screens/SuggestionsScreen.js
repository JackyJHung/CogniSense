import React, { useState, useEffect } from 'react';
import { View, Text, Button, ScrollView, ActivityIndicator, StyleSheet, Alert } from 'react-native';
import { getCurrentUser, getDailySuggestions } from '../api';
import Disclaimer from '../components/Disclaimer';

export default function SuggestionsScreen({ navigation }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const user = await getCurrentUser();
        const ds = await getDailySuggestions(user.id);
        setData(ds);
      } catch (e) {
        Alert.alert('Error', e?.response?.data?.detail ?? e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <View style={styles.center}><ActivityIndicator size="large" /></View>;
  }
  if (!data) {
    return (
      <View style={styles.container}>
        <Text>Could not load suggestions.</Text>
        <Button title="Back" onPress={() => navigation.goBack()} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.header}>Daily suggestions</Text>
      {data.suggestions.map((s, i) => (
        <Text key={i} style={styles.bullet}>• {s}</Text>
      ))}
      <Text style={styles.source}>Source: {data.lancet_risk_factor_source}</Text>
      <View style={{ height: 16 }} />
      <Button title="Back to dashboard" onPress={() => navigation.navigate('Dashboard')} />
      <Disclaimer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: '#fff' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 16 },
  bullet: { marginBottom: 10, lineHeight: 22 },
  source: { marginTop: 16, fontStyle: 'italic', fontSize: 11, color: '#555' },
});
