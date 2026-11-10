'use strict';

describe('browser-extension/profile-generator', () => {
  beforeAll(() => {
    loadBrowserScript('browser-extension/profile-data-us.js');
    loadBrowserScript('browser-extension/profile-generator.js');
  });

  test('generateProfile returns a complete US profile with the requested password length', () => {
    const profile = window.ProfileGenerator.generateProfile({ passwordLength: 20 });

    expect(profile.fullName).toMatch(/\S+\s+\S+/);
    expect(profile.country).toBe('United States');
    expect(profile.countryCode).toBe('US');
    expect(profile.state).toBeTruthy();
    expect(profile.city).toBeTruthy();
    expect(profile.addressLine1).toBeTruthy();
    expect(profile.postalCode).toMatch(/^\d{5}$/);
    expect(profile.password).toHaveLength(20);
  });

  test('generateProfile reuses the claimed email when provided', () => {
    const profile = window.ProfileGenerator.generateProfile({
      claimedEmail: 'claimed@example.com',
      passwordLength: 12,
    });

    expect(profile.email).toBe('claimed@example.com');
    expect(profile.password).toHaveLength(12);
  });

  test('generatePassword enforces lower and upper bounds', () => {
    const minPassword = window.ProfileGenerator.generatePassword(4, 1);
    const maxPassword = window.ProfileGenerator.generatePassword(99, 2);

    expect(minPassword).toHaveLength(8);
    expect(maxPassword).toHaveLength(32);
  });

  test('generatePassword includes lower, upper, numeric and symbol characters', () => {
    const password = window.ProfileGenerator.generatePassword(18, 7);

    expect(password).toMatch(/[a-z]/);
    expect(password).toMatch(/[A-Z]/);
    expect(password).toMatch(/\d/);
    expect(password).toMatch(/[!@#$%^&*()\-_=+]/);
  });

  test('normalizeProfile backfills fullName from firstName and lastName', () => {
    const profile = window.ProfileGenerator.normalizeProfile({
      firstName: 'Olivia',
      lastName: 'Smith',
      email: 'olivia@example.com',
    });

    expect(profile.fullName).toBe('Olivia Smith');
    expect(profile.country).toBe('United States');
    expect(profile.countryCode).toBe('US');
  });
});
