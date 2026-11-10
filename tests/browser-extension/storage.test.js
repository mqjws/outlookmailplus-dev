'use strict';

describe('browser-extension/storage', () => {
  let ExtensionStorage;

  beforeAll(() => {
    loadBrowserScript('browser-extension/storage.js');
    ExtensionStorage = window.ExtensionStorage;
  });

  beforeEach(() => {
    return chrome.storage.local.clear();
  });

  test('setLastGeneratedProfile and getLastGeneratedProfile round-trip data', async () => {
    const profile = { id: 'profile-1', fullName: 'Olivia Smith' };

    await ExtensionStorage.setLastGeneratedProfile(profile);

    await expect(ExtensionStorage.getLastGeneratedProfile()).resolves.toEqual(profile);
  });

  test('upsertSavedProfile updates an existing record with the same id', async () => {
    await ExtensionStorage.upsertSavedProfile({ id: 'same-id', fullName: 'Old Name' });
    const next = await ExtensionStorage.upsertSavedProfile({ id: 'same-id', fullName: 'New Name' });

    expect(next).toHaveLength(1);
    expect(next[0].fullName).toBe('New Name');
  });

  test('upsertSavedProfile keeps at most 20 saved profiles', async () => {
    for (let index = 0; index < 25; index += 1) {
      await ExtensionStorage.upsertSavedProfile({ id: `profile-${index}`, fullName: `User ${index}` });
    }

    const savedProfiles = await ExtensionStorage.getSavedProfiles();
    expect(savedProfiles).toHaveLength(20);
    expect(savedProfiles[0].id).toBe('profile-24');
    expect(savedProfiles[savedProfiles.length - 1].id).toBe('profile-5');
  });

  test('deleteSavedProfile removes only the requested item', async () => {
    await ExtensionStorage.upsertSavedProfile({ id: 'keep-me', fullName: 'Keep' });
    await ExtensionStorage.upsertSavedProfile({ id: 'remove-me', fullName: 'Remove' });

    const next = await ExtensionStorage.deleteSavedProfile('remove-me');

    expect(next).toHaveLength(1);
    expect(next[0].id).toBe('keep-me');
  });
});
