import React from 'react';
import { Text, View, StyleSheet } from 'react-native';

export default function Disclaimer() {
  return (
    <View style={styles.box}>
      <Text style={styles.text}>
        CogniSense is a self-tracking tool, NOT a medical diagnostic device. Any output is a suggestion,
        not professional advice. If you notice worsening memory concerns, please consult a licensed physician.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { padding: 12, marginTop: 16, backgroundColor: '#edf2f7', borderRadius: 6 },
  text: { fontSize: 11, fontStyle: 'italic', color: '#4a5568' },
});
